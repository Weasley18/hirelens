/**
 * Production traffic to the ML service must be encrypted, except to a single-label host such as
 * `http://ml:8000`: a container name that only resolves on the private Docker network, so the
 * request never leaves the machine.
 */
export function isAllowedProductionMlUrl(value: string): boolean {
  let url: URL;
  try { url = new URL(value); } catch { return false; }
  if (url.protocol === "https:") return true;
  return url.protocol === "http:" && /^[a-z][a-z0-9-]*$/.test(url.hostname) && url.hostname !== "localhost";
}
