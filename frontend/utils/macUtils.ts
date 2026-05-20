export const MAC_REGEX = /^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/;

export function isValidMac(mac: string): boolean {
  return MAC_REGEX.test(mac);
}

export function isCompleteMac(mac: string): boolean {
  return mac.split(":").every((seg) => seg.length === 2);
}
