const Slo = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const wlo = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function o3(i: Uint8Array, e = true, t = false) {
  const n = t ? Slo : wlo;

  let s = "";
  const r = i.byteLength % 3;

  let o = 0;
  for (; o < i.byteLength - r; o += 3) {
    const a = i[o + 0];
    const u = i[o + 1];
    const d = i[o + 2];

    s += n[a >>> 2];
    s += n[((a << 4) | (u >>> 4)) & 63];
    s += n[((u << 2) | (d >>> 6)) & 63];
    s += n[d & 63];
  }

  if (r === 1) {
    const a = i[o + 0];
    s += n[a >>> 2];
    s += n[(a << 4) & 63];
    e && (s += "==");
  } else if (r === 2) {
    const a = i[o + 0];
    const u = i[o + 1];
    s += n[a >>> 2];
    s += n[((a << 4) | (u >>> 4)) & 63];
    s += n[(u << 2) & 63];
    e && (s += "=");
  }

  return s;
}

class CustomBuffer {
  buffer: Uint8Array;
  byteLength: number;
  constructor(data: Uint8Array) {
    this.buffer = data;
    this.byteLength = data.byteLength;
  }
}

function wrap(data: any) {
  if (!(data instanceof ArrayBuffer)) {
    if (ArrayBuffer.isView(data)) {
      data = data.buffer.slice(
        data.byteOffset,
        data.byteOffset + data.byteLength
      );
    } else {
      throw new Error("Data must be an ArrayBuffer or ArrayBufferView");
    }
  }

  return new CustomBuffer(new Uint8Array(data));
}

function base64URLEncode(k: Uint8Array) {
  wrap(k);
  return o3(k, false, true);
}

let K = new Uint8Array(32);
K = crypto.getRandomValues(K);

async function sha256(inputString: string) {
  if (!crypto.subtle) {
    throw new Error(
      "'crypto.subtle' is not available so webviews will not work."
    );
  }

  const encoder = new TextEncoder();
  const encodedData = encoder.encode(inputString);
  const hashBuffer = await crypto.subtle.digest("SHA-256", encodedData);

  return hashBuffer;
}

export { K, sha256, base64URLEncode, o3, wrap, CustomBuffer };
