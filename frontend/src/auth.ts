import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
} from "oidc-client-ts";
import type { RuntimeConfig } from "./types";
let manager: UserManager | undefined;
let localToken: string | undefined;
export function setupAuth(config: RuntimeConfig) {
  if (!config.demo)
    manager = new UserManager({
      authority: config.authority,
      client_id: config.client_id,
      redirect_uri: window.location.origin + "/auth/callback",
      post_logout_redirect_uri: window.location.origin,
      response_type: "code",
      scope: config.scope,
      automaticSilentRenew: false,
      loadUserInfo: false,
      userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    });
}
export async function token(): Promise<string | undefined> {
  if (localToken) return localToken;
  const u = await manager?.getUser();
  return u && !u.expired ? u.access_token : undefined;
}
export async function signIn(demo: boolean) {
  if (demo) {
    localToken = "local-demo";
    return;
  }
  await manager?.clearStaleState();
  await manager?.signinRedirect();
}
export async function callback() {
  if (window.location.pathname === "/auth/callback" && manager) {
    await manager.signinRedirectCallback();
    window.history.replaceState({}, "", "/");
  }
}
export async function signOut() {
  localToken = undefined;
  if (manager) await manager.signoutRedirect();
}
