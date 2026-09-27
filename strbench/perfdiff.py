"""Per-symbol CPU seconds: fat build minus baseline build, from two perf runs.
usage: perfdiff.py BASE.data FAT.data FREQ [N]"""
import subprocess, sys
def load(path):
    out = subprocess.run(["perf", "report", "-i", path, "--no-children", "--stdio",
                          "--sort", "symbol", "-F", "overhead,sample"],
                         capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0].endswith('%') and p[2] == '[.]':
            d[p[3]] = d.get(p[3], 0) + int(p[1])
    return d
b, f = load(sys.argv[1]), load(sys.argv[2]); F = float(sys.argv[3]); n = int(sys.argv[4]) if len(sys.argv) > 4 else 16
print("total: base %.3fs  fat %.3fs" % (sum(b.values())/F, sum(f.values())/F))
diff = sorted(((f.get(k,0)-b.get(k,0))/F, k) for k in set(b) | set(f))
print("--- increases");  [print("%+7.3f  fat=%.3f  %s" % (d, f.get(k,0)/F, k[:95])) for d, k in diff[::-1][:n]]
print("--- decreases");  [print("%+7.3f  base=%.3f %s" % (d, b.get(k,0)/F, k[:95])) for d, k in diff[:8]]
