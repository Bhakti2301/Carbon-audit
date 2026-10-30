const PATHS = {
  leaf: <><path d="M5 21c.5-4.5 2.5-8 7-10" /><path d="M9 18c6.2 0 10.5-3.3 11-12-4.6 0-11 .8-11 7 0 1.6.6 3.3 1 5z" /></>,
  calc: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 7h8M8 11h2M12 11h2M8 15h2M12 15h2M8 18h8" /></>,
  file: <><path d="M14 3v4a1 1 0 0 0 1 1h4" /><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2z" /><path d="M9 13h6M9 17h6" /></>,
  factory: <path d="M3 21h18M5 21V9l5 3V9l5 3V5h4v16" />,
  truck: <><path d="M3 7h11v9H3zM14 10h4l3 3v3h-7" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
  building: <><rect x="5" y="3" width="14" height="18" rx="1" /><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2" /></>,
  bolt: <path d="M13 3 5 14h6l-1 7 8-11h-6z" />,
  plant: <path d="M12 21V9M12 13c-4 0-6-3-6-6 4 0 6 2 6 6zM12 11c0-4 2-6 6-6 0 3-2 6-6 6z" />,
  bank: <path d="M3 10 12 4l9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 21h18" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  print: <><path d="M7 9V3h10v6" /><rect x="3" y="9" width="18" height="8" rx="2" /><path d="M7 14h10v7H7z" /></>,
  back: <path d="M15 6l-6 6 6 6" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3" />,
  grid: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  layers: <><path d="m12 4 8 4-8 4-8-4z" /><path d="m4 12 8 4 8-4M4 16l8 4 8-4" /></>,
  history: <><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5" /><path d="M4 4v4.5h4.5M12 8v4l3 2" /></>,
  pin: <><path d="M12 21s-6-5.3-6-11a6 6 0 0 1 12 0c0 5.7-6 11-6 11z" /><circle cx="12" cy="10" r="2.2" /></>,
  spark: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  clip: <path d="m20 11-8.5 8.5a5 5 0 0 1-7-7L13 4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L14.5 7" />,
  check: <path d="m5 12 4.5 4.5L19 7" />,
  alert:<><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></>,
}

export default function Icon({ name, size = 18, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {PATHS[name]}
    </svg>
  )
}
