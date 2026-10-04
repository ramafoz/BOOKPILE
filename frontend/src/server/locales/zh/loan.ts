import type { LoanCopyKey } from "../../loanCopy";

export const loanZh = {
  loadFailed: "无法加载借阅数据。", unknown: "未知", loanHistory: "借阅记录", onLoanTo: "借给 {borrower}", onLoan: "借出中", since: "自 {date} 起", expected: "预计 {date} 归还", overdue: "已逾期", returnedRecord: "{loaned} 借出 · {returned} 归还", loanedTo: "借给 *", loanDate: "借出日期", optionalUnknown: "可选／未知", expectedReturn: "预计归还", optional: "可选", privateNotes: "所有者私人备注", close: "关闭", sharedCustody: "共享实体保管", loans: "借阅", currentLoan: "当前借阅", returnedDate: "归还日期", leaveBlankUnknown: "未知时留空", cancelLoanConfirm: "取消此借阅且不保留记录？", cancelLoan: "取消借阅", returnBook: "归还图书", loanThisBook: "借出此书", startLoan: "开始借阅", correctHistorical: "修正历史借阅", addHistorical: "添加历史借阅", cancelEdit: "取消编辑", saveCorrection: "保存修正", addHistory: "添加到记录", returnedLoans: "已归还借阅", edit: "编辑", deleteHistorical: "删除历史借阅", deleteHistoricalConfirm: "永久删除此历史借阅？",
} satisfies Record<LoanCopyKey, string>;
