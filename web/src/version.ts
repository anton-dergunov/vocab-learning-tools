export const appVersion = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "0.0.0";
export const appBuild = typeof __APP_BUILD__ === "string" ? __APP_BUILD__ : "0";
export const appVersionLabel = () => `${appVersion} (${appBuild})`;
