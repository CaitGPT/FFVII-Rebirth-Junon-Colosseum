// CityHash64 (Google, MIT licence), the hash UE4 uses for FName strings.
// Port of the reference implementation for the lengths an FName can have.
namespace TrainingDummy.DataBuilder;

internal static class CityHash
{
    const ulong K0 = 0xc3a5c85c97cb3127UL, K1 = 0xb492b66fbe98f273UL, K2 = 0x9ae16a3b2f90404fUL;

    static ulong F64(byte[] s, int i) => BitConverter.ToUInt64(s, i);
    static ulong F32(byte[] s, int i) => BitConverter.ToUInt32(s, i);
    static ulong Rot(ulong v, int shift) => shift == 0 ? v : (v >> shift) | (v << (64 - shift));
    static ulong ShiftMix(ulong v) => v ^ (v >> 47);
    static ulong Swap(ulong v) => System.Buffers.Binary.BinaryPrimitives.ReverseEndianness(v);

    static ulong Hash16(ulong u, ulong v, ulong mul = 0x9ddfea08eb382d69UL)
    {
        var a = (u ^ v) * mul; a ^= a >> 47;
        var b = (v ^ a) * mul; b ^= b >> 47;
        return b * mul;
    }

    static ulong Len0To16(byte[] s)
    {
        var len = (ulong)s.Length;
        if (s.Length >= 8)
        {
            var mul = K2 + len * 2; var a = F64(s, 0) + K2; var b = F64(s, s.Length - 8);
            var c = Rot(b, 37) * mul + a; var d = (Rot(a, 25) + b) * mul;
            return Hash16(c, d, mul);
        }
        if (s.Length >= 4)
        {
            var mul = K2 + len * 2; var a = F32(s, 0);
            return Hash16(len + (a << 3), F32(s, s.Length - 4), mul);
        }
        if (s.Length > 0)
        {
            uint a = s[0], b = s[s.Length >> 1], c = s[s.Length - 1];
            uint y = a + (b << 8), z = (uint)len + (c << 2);
            return ShiftMix(y * K2 ^ z * K0) * K2;
        }
        return K2;
    }

    static ulong Len17To32(byte[] s)
    {
        var len = (ulong)s.Length; var mul = K2 + len * 2;
        var a = F64(s, 0) * K1; var b = F64(s, 8); var c = F64(s, s.Length - 8) * mul; var d = F64(s, s.Length - 16) * K2;
        return Hash16(Rot(a + b, 43) + Rot(c, 30) + d, a + Rot(b + K2, 18) + c, mul);
    }

    static ulong Len33To64(byte[] s)
    {
        var len = (ulong)s.Length; var mul = K2 + len * 2;
        var a = F64(s, 0) * K2; var b = F64(s, 8); var c = F64(s, s.Length - 24); var d = F64(s, s.Length - 32);
        var e = F64(s, 16) * K2; var f = F64(s, 24) * 9; var g = F64(s, s.Length - 8); var h = F64(s, s.Length - 16) * mul;
        var u = Rot(a + g, 43) + (Rot(b, 30) + c) * 9; var v = ((a + g) ^ d) + f + 1;
        var w = Swap((u + v) * mul) + h; var x = Rot(e + f, 42) + c;
        var y = (Swap((v + w) * mul) + g) * mul; var z = e + f + c;
        a = Swap((x + z) * mul + y) + b;
        b = ShiftMix((z + a) * mul + d + h) * mul;
        return b + x;
    }

    static (ulong, ulong) WeakHash(byte[] s, int i, ulong a, ulong b)
    {
        ulong w = F64(s, i), x = F64(s, i + 8), y = F64(s, i + 16), z = F64(s, i + 24);
        a += w; b = Rot(b + a + z, 21); var c = a; a += x; a += y; b += Rot(a, 44);
        return (a + z, b + c);
    }

    public static ulong Hash64(byte[] s)
    {
        if (s.Length <= 16) return Len0To16(s);
        if (s.Length <= 32) return Len17To32(s);
        if (s.Length <= 64) return Len33To64(s);
        var len = (ulong)s.Length;
        var x = F64(s, s.Length - 40); var y = F64(s, s.Length - 16) + F64(s, s.Length - 56);
        var z = Hash16(F64(s, s.Length - 48) + len, F64(s, s.Length - 24));
        var v = WeakHash(s, s.Length - 64, len, z); var w = WeakHash(s, s.Length - 32, y + K1, x);
        x = x * K1 + F64(s, 0);
        var remaining = (s.Length - 1) & ~63; var i = 0;
        do
        {
            x = Rot(x + y + v.Item1 + F64(s, i + 8), 37) * K1; y = Rot(y + v.Item2 + F64(s, i + 48), 42) * K1;
            x ^= w.Item2; y += v.Item1 + F64(s, i + 40); z = Rot(z + w.Item1, 33) * K1;
            v = WeakHash(s, i, v.Item2 * K1, x + w.Item1); w = WeakHash(s, i + 32, z + w.Item2, y + F64(s, i + 16));
            (z, x) = (x, z); i += 64; remaining -= 64;
        } while (remaining != 0);
        return Hash16(Hash16(v.Item1, w.Item1) + ShiftMix(y) * K1 + z, Hash16(v.Item2, w.Item2) + x);
    }
}
