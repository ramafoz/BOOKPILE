import { useEffect, useRef, useState } from "react";
import { useLocale } from "./LocaleContext";
import { type AppLocale, formatLocalDateTime, intlLocale } from "./locale";
import { type AdminAccountDetail, type AdminAccountPage, type AdminAccountSummary, serverApi } from "./serverApi";

type DirectoryCopy = {
  title: string;
  open: string;
  back: string;
  previous: string;
  next: string;
  empty: string;
  state: string;
  admin: string;
  yes: string;
  no: string;
  lastLogin: string;
  usage: string;
  quota: string;
  noData: string;
  caution: string;
  states: Record<AdminAccountSummary["state"], string>;
};

const copy: Record<AppLocale, DirectoryCopy> = {
  en: {
    title: "Accounts", open: "View accounts", back: "Back to accounts", previous: "Previous", next: "Next",
    empty: "No accounts on this page.", state: "Account status", admin: "Platform administrator", yes: "Yes", no: "No",
    lastLogin: "Last successful sign-in", usage: "Storage used", quota: "Storage quota", noData: "No data",
    caution: "Inactivity alone does not identify a test account.",
    states: { pending_verification: "Awaiting verification", active: "Active", suspended: "Suspended", pending_deletion: "Awaiting deletion", deleted: "Deleted" },
  },
  gl: {
    title: "Contas", open: "Ver contas", back: "Volver ás contas", previous: "Anterior", next: "Seguinte",
    empty: "Non hai contas nesta páxina.", state: "Estado da conta", admin: "Administración da plataforma", yes: "Si", no: "Non",
    lastLogin: "Último inicio de sesión correcto", usage: "Espazo usado", quota: "Cota de almacenamento", noData: "Sen datos",
    caution: "A inactividade por si soa non identifica unha conta de proba.",
    states: { pending_verification: "Pendente de verificación", active: "Activa", suspended: "Suspendida", pending_deletion: "Pendente de eliminación", deleted: "Eliminada" },
  },
  es: {
    title: "Cuentas", open: "Ver cuentas", back: "Volver a las cuentas", previous: "Anterior", next: "Siguiente",
    empty: "No hay cuentas en esta página.", state: "Estado de la cuenta", admin: "Permiso de administrador", yes: "Sí", no: "No",
    lastLogin: "Último inicio de sesión exitoso", usage: "Espacio usado", quota: "Cuota de almacenamiento", noData: "Sin datos",
    caution: "La inactividad por sí sola no identifica una cuenta de prueba.",
    states: { pending_verification: "Pendiente de verificación", active: "Activa", suspended: "Suspendida", pending_deletion: "Pendiente de eliminación", deleted: "Eliminada" },
  },
  pt: {
    title: "Contas", open: "Ver contas", back: "Voltar às contas", previous: "Anterior", next: "Seguinte",
    empty: "Não há contas nesta página.", state: "Estado da conta", admin: "Permissão de administrador", yes: "Sim", no: "Não",
    lastLogin: "Último início de sessão bem-sucedido", usage: "Espaço usado", quota: "Quota de armazenamento", noData: "Sem dados",
    caution: "A inatividade por si só não identifica uma conta de teste.",
    states: { pending_verification: "A aguardar verificação", active: "Ativa", suspended: "Suspensa", pending_deletion: "A aguardar eliminação", deleted: "Eliminada" },
  },
  ca: {
    title: "Comptes", open: "Mostra els comptes", back: "Torna als comptes", previous: "Anterior", next: "Següent",
    empty: "No hi ha comptes en aquesta pàgina.", state: "Estat del compte", admin: "Permís d’administració", yes: "Sí", no: "No",
    lastLogin: "Darrer inici de sessió correcte", usage: "Espai utilitzat", quota: "Quota d’emmagatzematge", noData: "Sense dades",
    caution: "La inactivitat per si sola no identifica un compte de prova.",
    states: { pending_verification: "Pendent de verificació", active: "Actiu", suspended: "Suspès", pending_deletion: "Pendent de supressió", deleted: "Suprimit" },
  },
  it: {
    title: "Account", open: "Visualizza gli account", back: "Torna agli account", previous: "Precedente", next: "Successiva",
    empty: "Nessun account in questa pagina.", state: "Stato dell’account", admin: "Permesso di amministrazione", yes: "Sì", no: "No",
    lastLogin: "Ultimo accesso riuscito", usage: "Spazio utilizzato", quota: "Quota di archiviazione", noData: "Nessun dato",
    caution: "La sola inattività non identifica un account di prova.",
    states: { pending_verification: "In attesa di verifica", active: "Attivo", suspended: "Sospeso", pending_deletion: "In attesa di eliminazione", deleted: "Eliminato" },
  },
  fr: {
    title: "Comptes", open: "Voir les comptes", back: "Revenir aux comptes", previous: "Précédente", next: "Suivante",
    empty: "Aucun compte sur cette page.", state: "État du compte", admin: "Droit d’administration", yes: "Oui", no: "Non",
    lastLogin: "Dernière connexion réussie", usage: "Espace utilisé", quota: "Quota de stockage", noData: "Aucune donnée",
    caution: "L’inactivité seule ne permet pas d’identifier un compte de test.",
    states: { pending_verification: "En attente de vérification", active: "Actif", suspended: "Suspendu", pending_deletion: "En attente de suppression", deleted: "Supprimé" },
  },
  eu: {
    title: "Kontuak", open: "Ikusi kontuak", back: "Itzuli kontuetara", previous: "Aurrekoa", next: "Hurrengoa",
    empty: "Ez dago konturik orri honetan.", state: "Kontuaren egoera", admin: "Administratzaile-baimena", yes: "Bai", no: "Ez",
    lastLogin: "Azken saio-hasiera arrakastatsua", usage: "Erabilitako espazioa", quota: "Biltegiratze-kuota", noData: "Daturik ez",
    caution: "Jarduerarik ezak bakarrik ez du proba-kontu bat identifikatzen.",
    states: { pending_verification: "Egiaztatzeko zain", active: "Aktibo", suspended: "Etenda", pending_deletion: "Ezabatzeko zain", deleted: "Ezabatuta" },
  },
  oc: {
    title: "Compdes", open: "Veir es compdes", back: "Tornar as compdes", previous: "Anteriora", next: "Següenta",
    empty: "Non i a cap de compde en aguesta pagina.", state: "Estat deth compde", admin: "Permís d’administracion", yes: "Òc", no: "Non",
    lastLogin: "Darrèr inici de session corrècte", usage: "Espaci utilizat", quota: "Quòta d’emmagazinatge", noData: "Sense donades",
    caution: "Era inactivitat soleta non permet identificar un compde de pròva.",
    states: { pending_verification: "Pendent de verificacion", active: "Actiu", suspended: "Suspenut", pending_deletion: "Pendent de supression", deleted: "Suprimit" },
  },
  zh: {
    title: "账户", open: "查看账户", back: "返回账户列表", previous: "上一页", next: "下一页",
    empty: "此页没有账户。", state: "账户状态", admin: "平台管理员权限", yes: "是", no: "否",
    lastLogin: "最近一次成功登录", usage: "已用空间", quota: "存储配额", noData: "暂无数据",
    caution: "仅凭不活跃无法判断账户是否为测试账户。",
    states: { pending_verification: "待验证", active: "正常", suspended: "已暂停", pending_deletion: "待删除", deleted: "已删除" },
  },
};

export default function AdminAccountDirectory({ busy, run }: {
  busy: boolean;
  run: (action: () => Promise<void>) => Promise<void>;
}) {
  const { locale } = useLocale();
  const words = copy[locale];
  const [page, setPage] = useState<AdminAccountPage | null>(null);
  const [offsets, setOffsets] = useState([0]);
  const [detail, setDetail] = useState<AdminAccountDetail | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const nextOffset = page?.next_offset ?? null;

  useEffect(() => {
    if (page) heading.current?.focus();
  }, [detail, page]);

  function loadPage(nextOffsets: number[]) {
    void run(async () => {
      const result = await serverApi.adminAccounts(nextOffsets[nextOffsets.length - 1]);
      setPage(result);
      setOffsets(nextOffsets);
    });
  }

  function formatBytes(bytes: number | null) {
    if (bytes === null) return words.noData;
    const unit = bytes >= 1_000_000 ? "megabyte" : bytes >= 1_000 ? "kilobyte" : "byte";
    const divisor = unit === "megabyte" ? 1_000_000 : unit === "kilobyte" ? 1_000 : 1;
    return new Intl.NumberFormat(intlLocale(locale), { style: "unit", unit, maximumFractionDigits: 2 })
      .format(bytes / divisor);
  }

  return <section className="server-admin-accounts" aria-labelledby="admin-accounts-heading" aria-busy={busy}>
    <h3 id="admin-accounts-heading" tabIndex={-1} ref={heading}>{detail?.username ?? words.title}</h3>
    {detail ? <>
      <p>{words.caution}</p>
      <dl className="server-admin-account-facts">
        <dt>{words.state}</dt><dd>{words.states[detail.state]}</dd>
        <dt>{words.admin}</dt><dd>{detail.is_system_admin ? words.yes : words.no}</dd>
        <dt>{words.lastLogin}</dt><dd>{detail.last_successful_login_at
          ? <time dateTime={detail.last_successful_login_at}>{formatLocalDateTime(detail.last_successful_login_at, locale)}</time>
          : words.noData}</dd>
        <dt>{words.usage}</dt><dd>{formatBytes(detail.storage_used_bytes)}</dd>
        <dt>{words.quota}</dt><dd>{formatBytes(detail.storage_limit_bytes)}</dd>
      </dl>
      <button type="button" disabled={busy} onClick={() => setDetail(null)}>{words.back}</button>
    </> : page ? <>
      {page.accounts.length ? <ul>
        {page.accounts.map((account) => <li key={account.account_id}>
          <button type="button" disabled={busy} onClick={() => {
            void run(async () => setDetail(await serverApi.adminAccountDetail(account.account_id)));
          }}>
            <strong>{account.username}</strong>
            <span>{words.states[account.state]}{account.is_system_admin && <> · {words.admin}</>}</span>
          </button>
        </li>)}
      </ul> : <p>{words.empty}</p>}
      <div className="server-admin-account-pages">
        {offsets.length > 1 && <button type="button" disabled={busy}
          onClick={() => loadPage(offsets.slice(0, -1))}>{words.previous}</button>}
        {nextOffset !== null && <button type="button" disabled={busy}
          onClick={() => loadPage([...offsets, nextOffset])}>{words.next}</button>}
      </div>
    </> : <button type="button" disabled={busy} onClick={() => loadPage([0])}>{words.open}</button>}
  </section>;
}
