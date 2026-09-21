export const LOCALE_STORAGE_KEY = "bookpile.server.locale";

export const availableLocales = ["en", "gl"] as const;
export type AppLocale = (typeof availableLocales)[number];

export const localeNames: Record<AppLocale, string> = {
  en: "English",
  gl: "Galego",
};

const intlLocales: Record<AppLocale, string> = { en: "en-GB", gl: "gl-ES" };

export function parseLocale(value: string | null | undefined): AppLocale | null {
  const base = value?.trim().toLowerCase().split(/[-_]/)[0];
  return base === "en" || base === "gl" ? base : null;
}

export function resolveLocale(
  saved: string | null | undefined,
  browserLanguages: readonly string[] = [],
): AppLocale {
  const preference = parseLocale(saved);
  if (preference) return preference;
  for (const language of browserLanguages) {
    const supported = parseLocale(language);
    if (supported) return supported;
  }
  return "en";
}

export function formatLocalDateTime(value: string | Date, locale: AppLocale): string {
  return new Intl.DateTimeFormat(intlLocales[locale], {
    dateStyle: "medium", timeStyle: "short",
  }).format(new Date(value));
}

export function formatLocalNumber(value: number, locale: AppLocale): string {
  return new Intl.NumberFormat(intlLocales[locale]).format(value);
}

export const english = {
  languageLabel: "Language",
  storyLabel: "BOOKPILE introduction",
  storyEyebrow: "Your personal library, securely mapped",
  storyTitle: "Every book has its place.",
  storyDescription: "The hosted BOOKPILE is being built as a private, invitation-only service. Your account is the first boundary around your library.",
  previewNote: "Server preview · Accounts are separate from BOOKPILE Local v1",
  loading: "Opening BOOKPILE…",
  tryAgain: "Try again",
  welcomeBack: "Welcome back",
  signIn: "Sign in",
  loginIntro: "Enter the private account created from your beta invitation.",
  usernameOrEmail: "Username or email",
  password: "Password",
  keepSignedIn: "Keep me signed in on this device",
  forgotPassword: "Forgot password?",
  verifyAccount: "Verify account",
  useInvitation: "Use an invitation",
  tooManyAttemptsMinutesOne: "Too many attempts. Please try again in about {minutes} minute.",
  tooManyAttemptsMinutesMany: "Too many attempts. Please try again in about {minutes} minutes.",
  tooManyAttempts: "Too many attempts. Please wait before trying again.",
  serverUnavailable: "BOOKPILE could not reach the server. Please try again.",
  email: "Email",
  username: "Username",
  confirmPassword: "Confirm password",
  continueToSignIn: "Continue to sign in",
  backToSignIn: "Back to sign in",
  returnToSignIn: "Return to sign in",
  invitationBeta: "Invitation-only beta",
  createAccount: "Create your account",
  registrationIntro: "All fields are required. Use the single-use account invitation issued by a BOOKPILE administrator; a library invitation cannot create an account.",
  invitationToken: "Account invitation token",
  passwordHelp: "Use 12–128 characters. Spaces and Unicode characters are welcome.",
  registrationEmailSent: "Your account was created. Check your email to verify it before signing in.",
  registrationEmailFailed: "Your account was created, but the verification email could not be sent. Use Verify account to request another link.",
  accountVerification: "Account verification",
  accountRecovery: "Account recovery",
  requestNewLink: "Request a new link",
  resetYourPassword: "Reset your password",
  verificationRequestIntro: "We will send a fresh verification link if the account is eligible.",
  resetRequestIntro: "We will send a password-reset link if the account exists and is active.",
  genericEmailResponse: "If that email belongs to an eligible BOOKPILE account, a message is on its way.",
  sendLink: "Send link",
  confirmAddress: "Confirm your address",
  chooseNewPassword: "Choose a new password",
  verifyEmail: "Verify email",
  resetPassword: "Reset password",
  verifyEmailIntro: "Confirm this one-time link to activate your BOOKPILE account.",
  resetPasswordIntro: "Reset links expire after 30 minutes and can only be used once.",
  emailVerified: "Your email is verified. You can now sign in.",
  passwordChanged: "Your password has been changed and all previous sessions were signed out.",
  newPassword: "New password",
  confirmNewPassword: "Confirm new password",
  verifyMyEmail: "Verify my email",
  changePassword: "Change password",
  invalidToken: "This link does not contain a valid token.",
  recoveryWindow: "48-hour recovery",
  restoreAccount: "Restore account",
  restoreIntro: "This one-time link is the only way to restore a deleted account during its 48-hour recovery window.",
  accountRestored: "Your account and available library memberships were restored.",
  restoreHelp: "Confirm restoration, then sign in normally with your existing credentials.",
  keepDeletion: "Keep deletion and return",
  incompleteRecoveryLink: "This recovery link is incomplete. Use the exact link sent to your registered email address.",
  invalidCredentials: "Incorrect username or password.",
  actionFailed: "We could not complete this request. Check the details and try again.",
} as const;

export type MessageKey = keyof typeof english;

const galician: Record<MessageKey, string> = {
  languageLabel: "Idioma",
  storyLabel: "Presentación de BOOKPILE",
  storyEyebrow: "A túa biblioteca persoal, situada con seguridade",
  storyTitle: "Cada libro ten o seu lugar.",
  storyDescription: "BOOKPILE en liña está a construírse como un servizo privado ao que só se accede por convite. A túa conta é a primeira barreira de protección da túa biblioteca.",
  previewNote: "Versión de proba Server · As contas son independentes de BOOKPILE Local v1",
  loading: "Abrindo BOOKPILE…",
  tryAgain: "Tentar de novo",
  welcomeBack: "Dámosche a benvida",
  signIn: "Iniciar sesión",
  loginIntro: "Accede á conta privada creada co teu convite para a beta.",
  usernameOrEmail: "Nome de usuario ou correo electrónico",
  password: "Contrasinal",
  keepSignedIn: "Manter a sesión iniciada neste dispositivo",
  forgotPassword: "Esqueciches o contrasinal?",
  verifyAccount: "Verificar a conta",
  useInvitation: "Usar un convite",
  tooManyAttemptsMinutesOne: "Demasiados intentos. Téntao de novo dentro de aproximadamente {minutes} minuto.",
  tooManyAttemptsMinutesMany: "Demasiados intentos. Téntao de novo dentro de aproximadamente {minutes} minutos.",
  tooManyAttempts: "Demasiados intentos. Agarda antes de tentalo de novo.",
  serverUnavailable: "BOOKPILE non puido conectar co servidor. Téntao de novo.",
  email: "Correo electrónico",
  username: "Nome de usuario",
  confirmPassword: "Confirmar o contrasinal",
  continueToSignIn: "Continuar e iniciar sesión",
  backToSignIn: "Volver ao inicio de sesión",
  returnToSignIn: "Volver ao inicio de sesión",
  invitationBeta: "Beta só por convite",
  createAccount: "Crear a túa conta",
  registrationIntro: "Todos os campos son obrigatorios. Usa o convite dun só uso emitido por unha persoa administradora de BOOKPILE; un convite para unha biblioteca non permite crear unha conta.",
  invitationToken: "Código do convite para a conta",
  passwordHelp: "Usa entre 12 e 128 caracteres. Podes empregar espazos e caracteres Unicode.",
  registrationEmailSent: "A túa conta xa está creada. Consulta o correo para verificala antes de iniciar sesión.",
  registrationEmailFailed: "A túa conta xa está creada, pero non puidemos enviar o correo de verificación. Usa «Verificar a conta» para solicitar outra ligazón.",
  accountVerification: "Verificación da conta",
  accountRecovery: "Recuperación da conta",
  requestNewLink: "Solicitar outra ligazón",
  resetYourPassword: "Restablecer o contrasinal",
  verificationRequestIntro: "Enviaremos unha nova ligazón de verificación se a conta reúne os requisitos.",
  resetRequestIntro: "Enviaremos unha ligazón para restablecer o contrasinal se a conta existe e está activa.",
  genericEmailResponse: "Se ese correo pertence a unha conta de BOOKPILE que reúne os requisitos, recibirá unha mensaxe.",
  sendLink: "Enviar ligazón",
  confirmAddress: "Confirmar o enderezo",
  chooseNewPassword: "Escolle un contrasinal novo",
  verifyEmail: "Verificar o correo",
  resetPassword: "Restablecer o contrasinal",
  verifyEmailIntro: "Confirma esta ligazón dun só uso para activar a túa conta de BOOKPILE.",
  resetPasswordIntro: "As ligazóns para restablecer o contrasinal caducan aos 30 minutos e só se poden usar unha vez.",
  emailVerified: "O teu correo está verificado. Xa podes iniciar sesión.",
  passwordChanged: "Cambiaches o contrasinal e pecháronse todas as sesións anteriores.",
  newPassword: "Contrasinal novo",
  confirmNewPassword: "Confirmar o contrasinal novo",
  verifyMyEmail: "Verificar o meu correo",
  changePassword: "Cambiar o contrasinal",
  invalidToken: "Esta ligazón non contén un código válido.",
  recoveryWindow: "Recuperación de 48 horas",
  restoreAccount: "Restaurar a conta",
  restoreIntro: "Esta ligazón dun só uso é a única forma de restaurar unha conta eliminada durante o prazo de recuperación de 48 horas.",
  accountRestored: "Restauráronse a túa conta e as pertenzas ás bibliotecas que aínda estaban dispoñibles.",
  restoreHelp: "Confirma a restauración e despois inicia sesión coas túas credenciais habituais.",
  keepDeletion: "Manter a eliminación e volver",
  incompleteRecoveryLink: "Esta ligazón de recuperación está incompleta. Usa a ligazón exacta que enviamos ao teu correo rexistrado.",
  invalidCredentials: "O nome de usuario ou o contrasinal non son correctos.",
  actionFailed: "Non puidemos completar esta solicitude. Revisa os datos e téntao de novo.",
};

const catalogues: Record<AppLocale, Record<MessageKey, string>> = { en: english, gl: galician };

export function translate(
  locale: AppLocale,
  key: MessageKey,
  values: Record<string, string | number> = {},
): string {
  return catalogues[locale][key].replace(/\{(\w+)\}/g, (token, name: string) =>
    Object.hasOwn(values, name) ? String(values[name]) : token,
  );
}
