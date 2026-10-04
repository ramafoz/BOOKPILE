import type { InvitationCatalogue } from "../../invitationCopy";

export const invitationZh: InvitationCatalogue = {
  account: (url) => `我邀请您在 BOOKPILE 创建账户，在私人空间中整理个人藏书。邀请只能使用一次，并将在七天后过期。\n\n${url}`,
  library: (url, libraryName, role, scope) => {
    if (role === "OWNER") return `我邀请您以共同所有者身份共享 BOOKPILE 中的“${libraryName}”书库，并拥有相同的管理权限。邀请只能使用一次，并将在七天后过期。\n\n${url}`;
    const access = scope === "CATALOG_AND_MAP" ? "查看目录和实体地图" : "查看目录";
    return `我邀请您在 BOOKPILE 中${access}“${libraryName}”书库。邀请只能使用一次，并将在七天后过期。\n\n${url}`;
  },
};
