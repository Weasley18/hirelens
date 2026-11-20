export default function Lens({ processing = false, compact = false }) {
    return <div className={`lens-scene ${compact ? "lens-compact" : ""}`} aria-hidden="true">
    <div className="lens-axis axis-horizontal"/><div className="lens-axis axis-vertical"/>
    <div className="lens-orbit orbit-outer"/><div className="lens-orbit orbit-middle"/>
    <div className="lens-core">
      <svg className="lens-mark" width="76" height="76" viewBox="0 0 80 80" fill="none">
        <circle cx="32" cy="35" r="19" stroke="currentColor" strokeWidth="2"/>
        <circle cx="48" cy="35" r="19" stroke="currentColor" strokeWidth="2"/>
        <path d="M40 18c-10 9-10 25 0 34 10-9 10-25 0-34Z" fill="currentColor" opacity=".22"/>
        <path d="m54 52 12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    </div>
    {!compact && <><div className="lens-satellite satellite-one"><span /> EXPERIENCE</div>
    <div className="lens-satellite satellite-two"><span /> ROLE REQUIREMENTS</div>
    <div className="lens-coordinate coordinate-one">01 / CONTEXT</div>
    <div className="lens-coordinate coordinate-two">02 / ALIGNMENT</div></>}
    {(processing || compact) && <div className="lens-sweep"/>}
  </div>;
}
