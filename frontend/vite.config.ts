import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

type Edition = "local" | "server";

function editionFrontend(edition: Edition): Plugin {
  const virtualModuleId = "virtual:bookpile-entry";
  const resolvedVirtualModuleId = `\0${virtualModuleId}`;
  const title = edition === "local" ? "BOOKPILE · Personal Library" : "BOOKPILE · Server Preview";
  return {
    name: "bookpile-edition-frontend",
    resolveId(source) {
      if (source === virtualModuleId) {
        return resolvedVirtualModuleId;
      }
    },
    load(id) {
      if (id === resolvedVirtualModuleId) {
        return `import "/src/main.${edition}.tsx";`;
      }
    },
    transformIndexHtml(html) {
      return html.replace(/<title>.*?<\/title>/, `<title>${title}</title>`);
    },
  };
}

export default defineConfig(({ mode }) => {
  const edition: Edition = mode === "edition-local" ? "local" : "server";
  const local = edition === "local";
  const environment = loadEnv(mode, ".", "BOOKPILE_");
  const backendTarget = local
    ? environment.BOOKPILE_LOCAL_BACKEND_URL || "http://127.0.0.1:8000"
    : environment.BOOKPILE_SERVER_BACKEND_URL || "http://127.0.0.1:8100";
  return {
    plugins: [react(), editionFrontend(edition)],
    build: {
      outDir: `dist/${edition}`,
      emptyOutDir: true,
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          ...(local ? { rewrite: (path: string) => path.replace(/^\/api/, "") } : {}),
        },
      },
    },
    preview: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          ...(local ? { rewrite: (path: string) => path.replace(/^\/api/, "") } : {}),
        },
      },
    },
  };
});
