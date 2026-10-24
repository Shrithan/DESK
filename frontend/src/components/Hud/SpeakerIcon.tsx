export function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 9v6h4l5 5V4L8 9H4z" strokeLinejoin="round" />
      {!muted && <path d="M16.5 8.5a5 5 0 0 1 0 7" strokeLinecap="round" />}
      {muted && <path d="M18 9l4 6M22 9l-4 6" strokeLinecap="round" />}
    </svg>
  );
}
