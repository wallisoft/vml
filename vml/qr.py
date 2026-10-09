"""QR codes, made here: no library needed. Enough of the standard for an address or a line of text: bytes,
error correction M (about 15% of the picture can be lost), versions 1 to 10 (up to 213 characters).

    matrix(text)   -> a list of rows, each a list of True (dark) / False (light)
"""
# (total codewords, error-correction codewords per block, [(blocks, data codewords in each), ...]) for level M
VERSIONS = {1: (26, 10, [(1, 16)]), 2: (44, 16, [(1, 28)]), 3: (70, 26, [(1, 44)]), 4: (100, 18, [(2, 32)]),
            5: (134, 24, [(2, 43)]), 6: (172, 16, [(4, 27)]), 7: (196, 18, [(4, 31)]), 8: (242, 22, [(2, 38), (2, 39)]),
            9: (292, 22, [(3, 36), (2, 37)]), 10: (346, 26, [(4, 43), (1, 44)])}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
         9: [6, 26, 46], 10: [6, 28, 50]}

EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _ecc(data, count):
    """The Reed-Solomon codewords that follow a block of data."""
    gen = [1]                                                  # (x - a^0)(x - a^1)..., highest power first
    for i in range(count):
        nxt = [0] * (len(gen) + 1)
        for j, g in enumerate(gen):
            nxt[j] ^= g
            nxt[j + 1] ^= _mul(g, EXP[i])
        gen = nxt
    rest = list(data) + [0] * count
    for i in range(len(data)):
        lead = rest[i]
        if lead:
            for j, g in enumerate(gen):
                rest[i + j] ^= _mul(g, lead)
    return rest[len(data):]


def _codewords(raw, version):
    total, ec, groups = VERSIONS[version]
    capacity = sum(n * size for n, size in groups)
    bits = "0100" + format(len(raw), "016b" if version >= 10 else "08b") + "".join(format(b, "08b") for b in raw)
    bits += "0" * min(4, capacity * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    data = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    data += [pad[i % 2] for i in range(capacity - len(data))]
    blocks, at = [], 0
    for n, size in groups:
        for _ in range(n):
            block = data[at:at + size]
            at += size
            blocks.append((block, _ecc(block, ec)))
    out = []
    for i in range(max(len(b[0]) for b in blocks)):
        out += [b[0][i] for b in blocks if i < len(b[0])]
    for i in range(ec):
        out += [b[1][i] for b in blocks]
    return out


def _bch(value, poly, bits):
    """The remainder that protects the format (and version) information."""
    reg = value << bits
    top = poly.bit_length()
    for shift in range(reg.bit_length() - top, -1, -1):
        if reg >> (shift + top - 1) & 1:
            reg ^= poly << shift
    return reg


def _penalty(m):
    n, score = len(m), 0
    for rows in (m, [list(col) for col in zip(*m)]):               # runs of five or more, and finder look-alikes
        for row in rows:
            run, last = 0, None
            for cell in row:
                if cell == last:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, last = 1, cell
            if run >= 5:
                score += run - 2
            line = "".join("1" if c else "0" for c in row)
            score += 40 * (line.count("10111010000") + line.count("00001011101"))
    for y in range(n - 1):                                         # 2 x 2 blocks of one colour
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, m)) * 100 // (n * n)                       # far from half dark
    return score + 10 * (abs(dark - 50) // 5)


MASKS = [lambda y, x: (y + x) % 2 == 0, lambda y, x: y % 2 == 0, lambda y, x: x % 3 == 0, lambda y, x: (y + x) % 3 == 0,
         lambda y, x: (y // 2 + x // 3) % 2 == 0, lambda y, x: (y * x) % 2 + (y * x) % 3 == 0,
         lambda y, x: ((y * x) % 2 + (y * x) % 3) % 2 == 0, lambda y, x: ((y + x) % 2 + (y * x) % 3) % 2 == 0]


def matrix(text):
    raw = str(text).encode("utf-8")
    version = next((v for v in sorted(VERSIONS)
                    if len(raw) <= sum(n * s for n, s in VERSIONS[v][2]) - (3 if v >= 10 else 2)), None)
    if version is None:
        raise ValueError("that is too long for a QR code made here (213 characters at most)")
    n = 17 + 4 * version
    m = [[False] * n for _ in range(n)]
    fixed = [[False] * n for _ in range(n)]

    def put(y, x, dark):
        if 0 <= y < n and 0 <= x < n:
            m[y][x], fixed[y][x] = bool(dark), True

    for oy, ox in ((0, 0), (0, n - 7), (n - 7, 0)):                # the three corner squares, with their margins
        for y in range(-1, 8):
            for x in range(-1, 8):
                inside = 0 <= y <= 6 and 0 <= x <= 6
                put(oy + y, ox + x, inside and (y in (0, 6) or x in (0, 6) or (2 <= y <= 4 and 2 <= x <= 4)))
    centres = ALIGN[version]
    for cy in centres:                                             # the small squares that keep a big code straight
        for cx in centres:
            if fixed[cy][cx]:
                continue
            for y in range(-2, 3):
                for x in range(-2, 3):
                    put(cy + y, cx + x, max(abs(y), abs(x)) != 1)
    for i in range(8, n - 8):                                      # the dotted lines between the corners
        if not fixed[6][i]:
            put(6, i, i % 2 == 0)
        if not fixed[i][6]:
            put(i, 6, i % 2 == 0)
    put(n - 8, 8, True)
    for i in range(9):                                             # room for the format information
        for y, x in ((8, i), (i, 8), (8, n - 1 - i), (n - 1 - i, 8)):
            if i < 8 or (y, x) in ((8, 8),):
                if not fixed[y][x]:
                    fixed[y][x] = True
    if version >= 7:
        info = (version << 12) | _bch(version, 0x1F25, 12)
        for i in range(18):
            bit = info >> i & 1
            put(i // 3, n - 11 + i % 3, bit)
            put(n - 11 + i % 3, i // 3, bit)

    words = _codewords(raw, version)
    bits = [w >> (7 - i) & 1 for w in words for i in range(8)]
    at, x, up = 0, n - 1, True
    cells = []
    while x > 0:                                                   # the data, in two-wide columns from the right, snaking
        if x == 6:
            x -= 1
        for y in (range(n - 1, -1, -1) if up else range(n)):
            for xx in (x, x - 1):
                if not fixed[y][xx]:
                    m[y][xx] = bool(bits[at]) if at < len(bits) else False
                    at += 1
                    cells.append((y, xx))
        x -= 2
        up = not up

    best = None
    for mask, test in enumerate(MASKS):
        trial = [row[:] for row in m]
        for y, xx in cells:
            if test(y, xx):
                trial[y][xx] = not trial[y][xx]
        fmt = ((0b00 << 3 | mask) << 10 | _bch(0b00 << 3 | mask, 0x537, 10)) ^ 0x5412
        for i in range(15):
            bit = bool(fmt >> (14 - i) & 1)
            # around the top-left corner
            if i < 6:
                trial[8][i] = bit
            elif i == 6:
                trial[8][7] = bit
            elif i == 7:
                trial[8][8] = bit
            elif i == 8:
                trial[7][8] = bit
            else:
                trial[14 - i][8] = bit
            # and split between the other two
            if i < 7:
                trial[n - 1 - i][8] = bit
            else:
                trial[8][n - 15 + i] = bit
        trial[n - 8][8] = True
        score = _penalty(trial)
        if best is None or score < best[0]:
            best = (score, trial)
    return best[1]


def png(text, scale=6, margin=4):
    """The code as a PNG picture (its bytes): black on white, with the quiet margin a scanner needs."""
    import struct
    import zlib
    m = matrix(text)
    n = len(m)
    side = (n + 2 * margin) * scale
    rows = []
    for y in range(side):
        cy = y // scale - margin
        row = bytearray(b"\x00")
        for x in range(side):
            cx = x // scale - margin
            dark = 0 <= cy < n and 0 <= cx < n and m[cy][cx]
            row.append(0 if dark else 255)
        rows.append(bytes(row))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
