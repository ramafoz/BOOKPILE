import type { AppLocale } from "./locale";

export type LibraryInvitationRole = "OWNER" | "VIEWER";
export type LibraryInvitationScope = "CATALOG_ONLY" | "CATALOG_AND_MAP" | null;
type InvitationLocale = AppLocale;

export function accountInvitationMessage(locale: InvitationLocale, url: string): string {
  if (locale === "gl") {
    return `Convídote a crear unha conta en BOOKPILE, un espazo privado para organizar a túa biblioteca persoal. O convite é dun só uso e caduca aos sete días.\n\n${url}`;
  }
  if (locale === "es") {
    return `Te invito a crear una cuenta en BOOKPILE, un espacio privado para organizar tu biblioteca personal. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`;
  }
  if (locale === "pt") {
    return `Convido-te a criar uma conta no BOOKPILE, um espaço privado para organizar a tua biblioteca pessoal. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`;
  }
  return `I invite you to create an account on BOOKPILE, a private space for organising your personal library. This invitation can only be used once and expires after seven days.\n\n${url}`;
}

export function libraryInvitationMessage(
  locale: InvitationLocale,
  url: string,
  libraryName: string,
  role: LibraryInvitationRole,
  scope: LibraryInvitationScope,
): string {
  if (locale === "gl") {
    if (role === "OWNER") {
      return `Convídote a compartir a biblioteca «${libraryName}» en BOOKPILE como copropietario/a con iguais permisos de administración. Este convite é dun só uso e caduca aos sete días.\n\n${url}`;
    }
    const access = scope === "CATALOG_AND_MAP"
      ? "ver o catálogo e o mapa físico"
      : "ver o catálogo";
    return `Convídote a ${access} da biblioteca «${libraryName}» en BOOKPILE. Este convite é dun só uso e caduca aos sete días.\n\n${url}`;
  }
  if (locale === "es") {
    if (role === "OWNER") {
      return `Te invito a compartir la biblioteca «${libraryName}» en BOOKPILE como copropietario/a con los mismos permisos de administración. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`;
    }
    const access = scope === "CATALOG_AND_MAP"
      ? "ver el catálogo y el mapa físico"
      : "ver el catálogo";
    return `Te invito a ${access} de la biblioteca «${libraryName}» en BOOKPILE. La invitación solo se puede usar una vez y caduca a los siete días.\n\n${url}`;
  }
  if (locale === "pt") {
    if (role === "OWNER") {
      return `Convido-te a partilhar a biblioteca «${libraryName}» no BOOKPILE como coproprietário/a com a mesma autoridade administrativa. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`;
    }
    const access = scope === "CATALOG_AND_MAP"
      ? "ver o catálogo e o mapa físico"
      : "ver o catálogo";
    return `Convido-te a ${access} da biblioteca «${libraryName}» no BOOKPILE. O convite só pode ser usado uma vez e expira após sete dias.\n\n${url}`;
  }
  if (role === "OWNER") {
    return `I invite you to share the “${libraryName}” library on BOOKPILE as an equal co-Owner with the same administrative authority. This invitation can only be used once and expires after seven days.\n\n${url}`;
  }
  const access = scope === "CATALOG_AND_MAP"
    ? "view the catalogue and physical map of"
    : "view the catalogue of";
  return `I invite you to ${access} the “${libraryName}” library on BOOKPILE. This invitation can only be used once and expires after seven days.\n\n${url}`;
}
