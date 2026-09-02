import { X } from "lucide-react";

import { type TimedNotice } from "./timedNotices";

export default function TimedNoticeStack({ notices, onDismiss }: {
  notices: TimedNotice[];
  onDismiss: (id: number) => void;
}) {
  if (!notices.length) return null;
  return <div className="server-notice-stack" aria-live="polite">
    {notices.map((notice) => <div className="server-message success" key={notice.id}>
      <span>{notice.message}</span>
      <button type="button" onClick={() => onDismiss(notice.id)} aria-label="Dismiss notification"><X size={15} /></button>
    </div>)}
  </div>;
}
