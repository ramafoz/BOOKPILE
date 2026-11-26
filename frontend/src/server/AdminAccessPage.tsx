import { type FormEvent, useState } from "react";
import { useLocale } from "./LocaleContext";
import { type AppLocale, intlLocale } from "./locale";
import { ServerApiError, serverApi } from "./serverApi";

type AccessCopy = {
  title: string;
  useKey: string;
  registerKey: string;
  code: string;
  registered: string;
  check: string;
  end: string;
  expires: string;
  browser: string;
};

const copy: Record<AppLocale, AccessCopy> = {
  en: { title: "Platform access", useKey: "Use a passkey or security key", registerKey: "Register the first key", code: "Operator email confirmation code", registered: "Key registered. Continue to sign in with it.", check: "Check admin session", end: "End admin session", expires: "Session expires at", browser: "Open this page in a current browser over HTTPS." },
  gl: { title: "Acceso á plataforma", useKey: "Usar unha chave de acceso ou de seguridade", registerKey: "Rexistrar a primeira chave", code: "Código de confirmación do correo do operador", registered: "Chave rexistrada. Continúa para iniciar sesión con ela.", check: "Comprobar a sesión administrativa", end: "Pechar a sesión administrativa", expires: "A sesión caduca ás", browser: "Abre esta páxina nun navegador actualizado mediante HTTPS." },
  es: { title: "Acceso a la plataforma", useKey: "Usar una llave de acceso o de seguridad", registerKey: "Registrar la primera llave", code: "Código de confirmación del correo del operador", registered: "Llave registrada. Continúa para iniciar sesión con ella.", check: "Comprobar la sesión administrativa", end: "Cerrar la sesión administrativa", expires: "La sesión caduca a las", browser: "Abre esta página en un navegador actualizado mediante HTTPS." },
  pt: { title: "Acesso à plataforma", useKey: "Usar uma chave de acesso ou de segurança", registerKey: "Registar a primeira chave", code: "Código de confirmação do correio do operador", registered: "Chave registada. Continua para iniciar sessão com ela.", check: "Verificar a sessão administrativa", end: "Terminar a sessão administrativa", expires: "A sessão expira às", browser: "Abre esta página num navegador atualizado através de HTTPS." },
  ca: { title: "Accés a la plataforma", useKey: "Fes servir una clau d’accés o de seguretat", registerKey: "Registra la primera clau", code: "Codi de confirmació del correu de l’operador", registered: "Clau registrada. Continua per iniciar-hi la sessió.", check: "Comprova la sessió administrativa", end: "Tanca la sessió administrativa", expires: "La sessió caduca a les", browser: "Obre aquesta pàgina en un navegador actualitzat mitjançant HTTPS." },
  it: { title: "Accesso alla piattaforma", useKey: "Usa una passkey o una chiave di sicurezza", registerKey: "Registra la prima chiave", code: "Codice di conferma inviato all’operatore", registered: "Chiave registrata. Continua per accedere con la chiave.", check: "Controlla la sessione amministrativa", end: "Termina la sessione amministrativa", expires: "La sessione scade alle", browser: "Apri questa pagina in un browser aggiornato tramite HTTPS." },
  fr: { title: "Accès à la plateforme", useKey: "Utiliser une clé d’accès ou de sécurité", registerKey: "Enregistrer la première clé", code: "Code de confirmation envoyé à l’opérateur", registered: "Clé enregistrée. Continuez pour vous connecter avec cette clé.", check: "Vérifier la session d’administration", end: "Fermer la session d’administration", expires: "La session expire à", browser: "Ouvrez cette page en HTTPS dans un navigateur à jour." },
  eu: { title: "Plataformarako sarbidea", useKey: "Erabili sarbide-gakoa edo segurtasun-gakoa", registerKey: "Erregistratu lehen gakoa", code: "Operadorearen posta elektronikoko berrespen-kodea", registered: "Gakoa erregistratu da. Jarraitu gakoarekin saioa hasteko.", check: "Egiaztatu administrazio-saioa", end: "Amaitu administrazio-saioa", expires: "Saioa iraungitzeko ordua", browser: "Ireki orri hau nabigatzaile eguneratu batean HTTPS bidez." },
  oc: { title: "Accès ara plataforma", useKey: "Utiliza ua clau d’accès o de seguretat", registerKey: "Registra era prumèra clau", code: "Còdi de confirmacion deth corrèu der operador", registered: "Clau registrada. Contunha entà iniciar era session damb era clau.", check: "Verifica era session administrativa", end: "Barra era session administrativa", expires: "Era session expire tàs", browser: "Daurís aguesta pagina en un navegador actualizat per HTTPS." },
  zh: { title: "平台访问", useKey: "使用通行密钥或安全密钥", registerKey: "注册首个密钥", code: "操作员邮件确认码", registered: "密钥已注册。请继续使用该密钥登录。", check: "检查管理会话", end: "结束管理会话", expires: "会话到期时间", browser: "请使用最新版本的浏览器通过 HTTPS 打开此页面。" },
};

export default function AdminAccessPage() {
  const { locale, t } = useLocale();
  const words = copy[locale];
  const [options, setOptions] = useState<Awaited<ReturnType<typeof serverApi.adminOptions>> | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [registered, setRegistered] = useState(false);
  const [expires, setExpires] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(t(caught instanceof ServerApiError && caught.status === 429 ? "tooManyAttempts" : "actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  const supported = window.isSecureContext && typeof PublicKeyCredential !== "undefined"
    && typeof PublicKeyCredential.parseCreationOptionsFromJSON === "function"
    && typeof PublicKeyCredential.parseRequestOptionsFromJSON === "function"
    && typeof PublicKeyCredential.prototype.toJSON === "function";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!options) return;
    setOptions(null);
    setCode("");
    void run(async () => {
      const credential = options.ceremony === "registration"
        ? await navigator.credentials.create({ publicKey: PublicKeyCredential.parseCreationOptionsFromJSON(options.public_key) })
        : await navigator.credentials.get({ publicKey: PublicKeyCredential.parseRequestOptionsFromJSON(options.public_key) });
      if (!(credential instanceof PublicKeyCredential)) throw new Error();
      const result = await serverApi.verifyAdminAccess(credential.toJSON(), code || undefined);
      setRegistered(result.registered);
      if (!result.registered) setExpires((await serverApi.adminSession()).expires_at);
    });
  }

  return <section className="server-auth-card" aria-labelledby="admin-access-heading">
    <h2 id="admin-access-heading">{words.title}</h2>
    {!supported && <p>{words.browser}</p>}
    {error && <p className="server-message error" role="alert">{error}</p>}
    {registered && <p className="server-message success" role="status">{words.registered}</p>}
    {expires && <p role="status">{words.expires} {new Date(expires).toLocaleTimeString(intlLocale(locale))}</p>}
    {supported && (options ? <form className="server-form" onSubmit={submit}>
      {options.ceremony === "registration" && <label className="server-field">
        <span>{words.code}</span>
        <input type="password" autoComplete="off" required maxLength={128} value={code}
          onChange={(event) => setCode(event.target.value)} />
      </label>}
      <button type="submit" className="server-submit" disabled={busy}>
        {options.ceremony === "registration" ? words.registerKey : words.useKey}
      </button>
    </form> : <button className="server-submit" type="button" disabled={busy}
      onClick={() => { void run(async () => { setRegistered(false); setOptions(await serverApi.adminOptions()); }); }}>
      {words.useKey}
    </button>)}
    <div className="server-card-links">
      <button type="button" disabled={busy} onClick={() => { void run(async () => {
        setExpires(null);
        setExpires((await serverApi.adminSession()).expires_at);
      }); }}>{words.check}</button>
      <button type="button" disabled={busy} onClick={() => { void run(async () => {
        setExpires(null);
        await serverApi.adminLogout();
      }); }}>{words.end}</button>
      <a href="/">BOOKPILE</a>
    </div>
  </section>;
}
