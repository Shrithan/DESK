"""Local dual-camera map. Never turn independent box centers into metric XYZ."""
import time
import cv2
import numpy as np


def _array(value, shape, name):
    result=np.asarray(value,dtype=float)
    if result.shape!=shape or not np.isfinite(result).all():
        raise ValueError(f'{name} must be finite with shape {shape}')
    return result


class StereoCalibration:
    def __init__(self, payload):
        if payload.get('units')!='meters' or payload.get('axes')!='x-right_y-forward_z-up':
            raise ValueError('Calibration requires meters and x-right_y-forward_z-up axes')
        self.version=str(payload.get('version','local-v1'))
        self.cameras={}
        for name in ('front','top'):
            item=payload.get('cameras',{}).get(name,{})
            K=_array(item.get('K'),(3,3),f'{name}.K')
            R=_array(item.get('R_world_to_camera'),(3,3),f'{name}.R_world_to_camera')
            t=_array(item.get('t_world_to_camera_m'),(3,),f'{name}.t_world_to_camera_m')
            size=_array(item.get('image_size'),(2,),f'{name}.image_size')
            distortion=np.asarray(item.get('distortion',[0,0,0,0,0]),dtype=float)
            if (distortion.ndim!=1 or len(distortion) not in (4,5,8,12,14)
                    or not np.isfinite(distortion).all() or min(size)<=0
                    or K[0,0]<=0 or K[1,1]<=0
                    or not np.allclose(K[2],[0,0,1])
                    or not np.allclose(R@R.T,np.eye(3),atol=1e-4) or np.linalg.det(R)<.999):
                raise ValueError(f'Invalid camera calibration: {name}')
            self.cameras[name]=dict(K=K,R=R,t=t,size=size,distortion=distortion)
        centers=[-cam['R'].T@cam['t'] for cam in self.cameras.values()]
        if np.linalg.norm(centers[0]-centers[1])<.01:
            raise ValueError('Camera baseline must exceed one centimeter')

    def matrices(self,name,shape):
        camera=self.cameras[name]
        h,w=shape[:2]; ow,oh=camera['size']
        if abs(w/h-ow/oh)>.015:
            raise ValueError('Camera aspect ratio differs from calibration; recalibrate')
        K=np.diag([w/ow,h/oh,1.])@camera['K']
        P=K@np.column_stack((camera['R'],camera['t']))
        return camera,K,P

    def triangulate(self,a,b,shape_a,shape_b):
        c1,k1,p1=self.matrices('front',shape_a)
        c2,k2,p2=self.matrices('top',shape_b)
        a=cv2.undistortPoints(np.float64(a).reshape(1,1,2),k1,c1['distortion'],P=k1).reshape(2)
        b=cv2.undistortPoints(np.float64(b).reshape(1,1,2),k2,c2['distortion'],P=k2).reshape(2)
        homogeneous=cv2.triangulatePoints(p1,p2,a.reshape(2,1),b.reshape(2,1))[:,0]
        if abs(homogeneous[3])<1e-10:
            return None
        point=homogeneous[:3]/homogeneous[3]
        if not np.isfinite(point).all():return None
        errors=[];rays=[]
        for camera,P,pixel in ((c1,p1,a),(c2,p2,b)):
            if (camera['R']@point+camera['t'])[2]<=.001:return None
            projected=P@np.r_[point,1.]
            errors.append(float(np.linalg.norm(projected[:2]/projected[2]-pixel)))
            center=-camera['R'].T@camera['t']; ray=point-center
            rays.append(ray/np.linalg.norm(ray))
        angle=float(np.degrees(np.arccos(np.clip(np.dot(*rays),-1,1))))
        if max(errors)>2. or angle<1.:
            return None
        return dict(position_m=dict(zip(('x','y','z'),map(float,point))),
                    reprojection_error_px=max(errors),ray_angle_degrees=angle)


class WorkspaceMapper:
    def __init__(self):
        self.calibration=None
        self.anchor=None
        self.candidate=None
        self.hits=0
        self.last_pair=None
        self.cached=None
        self.detector=cv2.SIFT_create()

    def reset_anchor(self):
        self.anchor=self.candidate=self.last_pair=self.cached=None
        self.hits=0

    def configure(self,payload):
        self.calibration=StereoCalibration(payload)
        self.reset_anchor()
        return dict(status='calibrated',version=self.calibration.version)

    @staticmethod
    def view(session):
        active=session.frame is not None and time.monotonic()-session.last_received<.8
        obs=session.observation
        tracked=active and obs is not None and obs['tracking_state']=='tracked'
        view=dict(connected=active,tracked=tracked,label=session.object_label,
                  object_id=obs['object_id'] if obs else None,
                  detections=[],center_uv=None,contour_uv=[])
        if not active:return view
        h,w=session.frame.shape[:2]
        if time.monotonic()-session.last_detection<.8:
            view['detections']=[dict(label=d['label'],score=d['score'],
                  center_uv=[d['center'][0]/w,1-d['center'][1]/h]) for d in session.detections]
        if tracked:
            target=session.tracker.targets[(session.camera_id,obs['object_id'])]
            moment=cv2.moments(target.mask)
            if moment['m00']:
                view['center_uv']=[moment['m10']/moment['m00']/w,1-moment['m01']/moment['m00']/h]
            contours,_=cv2.findContours(target.mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                contour=cv2.approxPolyDP(max(contours,key=cv2.contourArea),2,True).reshape(-1,2)
                view['contour_uv']=[[float(x/w),float(1-y/h)] for x,y in contour]
        return view

    def snapshot(self,sessions):
        views={name:self.view(session) for name,session in sessions.items()}
        result=dict(views=views,map_mode='topdown_image_coordinates',units='normalized image coordinates',
                    calibration_loaded=self.calibration is not None,world=None,
                    status='Calibration needed for metric XYZ; the top map has no measured height',
                    timing='browser-sampled; sensor synchronization unverified')
        if self.calibration is None:return result
        result['map_mode']='calibrated_3d_estimate'
        if not all(v['tracked'] for v in views.values()):
            result['status']='Waiting for the target in both cameras'
            return result
        front,top=sessions['front'],sessions['top']
        samples=[s.capture_sample_ms for s in (front,top)]
        if any(s is None for s in samples) or abs(samples[0]-samples[1])>60:
            result['status']='Waiting for closely sampled frames'
            return result
        if front.object_label and top.object_label and front.object_label!=top.object_label:
            result['status']='Camera targets differ; cross-view association unresolved'
            return result
        object_ids=(front.observation['object_id'],top.observation['object_id'])
        if self.anchor and self.anchor['objects']!=object_ids:self.reset_anchor()
        fa={f['track_id']:f['pixel_xy'] for f in front.observation['features']}
        fb={f['track_id']:f['pixel_xy'] for f in top.observation['features']}
        if self.anchor:
            ia,ib=self.anchor['ids']
            if ia not in fa or ib not in fb:
                result['status']='Reference feature lost; reset mapping anchor to establish a new one'
                return result
            try:world=self.calibration.triangulate(fa[ia],fb[ib],front.frame.shape,top.frame.shape)
            except ValueError as exc:
                result['status']=str(exc);return result
            if world:
                world.update(anchor_id=f'{ia}|{ib}',confidence=None)
                result['world']=world
                result['status']='Calibrated surface-point estimate · camera timing unverified'
            else:result['status']='Reference failed depth / reprojection checks'
            return result
        pair=(front.frame_id,top.frame_id)
        if pair==self.last_pair:
            result['status']='Matching surface details across views…'
            return result
        self.last_pair=pair
        try:
            matches=self.match(front,top)
        except ValueError as exc:
            result['status']=str(exc);return result
        if len(matches)<6:
            self.hits=0;self.candidate=None
            result['status']='Not enough shared surface details; identity unresolved'
            return result
        ids=(matches[0][0],matches[0][1])
        # Prefer an existing confirmed candidate if it survives, rather than changing points.
        if self.candidate and any((m[0],m[1])==self.candidate for m in matches):ids=self.candidate
        self.hits=self.hits+1 if ids==self.candidate else 1
        self.candidate=ids
        if self.hits>=2:
            self.anchor=dict(objects=object_ids,ids=ids)
        result['status']='Confirming cross-camera surface reference…'
        return result

    def match(self,front,top):
        groups=[]
        for session in (front,top):
            features=session.observation['features']
            gray=cv2.cvtColor(session.frame,cv2.COLOR_BGR2GRAY)
            keys=[]
            for index,feature in enumerate(features):
                x,y=feature['pixel_xy']
                if not (0<=x<gray.shape[1] and 0<=y<gray.shape[0]):continue
                key=cv2.KeyPoint(x,y,12);key.class_id=index;keys.append(key)
            keys,descriptors=self.detector.compute(gray,keys)
            groups.append(([features[key.class_id] for key in keys],descriptors))
        (features_a,da),(features_b,db)=groups
        if da is None or db is None or len(db)<2:return []
        matcher=cv2.BFMatcher()
        reverse={m.queryIdx:m.trainIdx for m in matcher.match(db,da)}
        accepted=[]
        for pair in matcher.knnMatch(da,db,k=2):
            if len(pair)!=2:continue
            m,n=pair
            if m.distance>=.65*n.distance or reverse.get(m.trainIdx)!=m.queryIdx:continue
            a,b=features_a[m.queryIdx],features_b[m.trainIdx]
            point=self.calibration.triangulate(a['pixel_xy'],b['pixel_xy'],front.frame.shape,top.frame.shape)
            if point:accepted.append((a['track_id'],b['track_id'],m.distance))
        return sorted(accepted,key=lambda m:m[2])
