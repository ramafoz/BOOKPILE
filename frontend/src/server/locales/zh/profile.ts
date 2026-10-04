import type { ProfileCopyKey } from "../../profileCopy";

export const profileZh = {
  openFailed: "无法打开此个人资料。", closeProfile: "关闭个人资料", openingProfile: "正在打开个人资料…", member: "BOOKPILE 成员", timezone: "时区", gender: "性别", pronouns: "代词", city: "城市", state: "省／地区", country: "国家／地区", dateOfBirth: "出生日期", female: "女性", male: "男性", nonBinary: "非二元", other: "其他", they: "其", empty: "该成员未向您共享任何个人资料信息。",
} satisfies Record<ProfileCopyKey, string>;
