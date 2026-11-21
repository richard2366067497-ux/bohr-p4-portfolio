import math
import random

SEED = 20240517
Z95 = 1.959963984540054

def _betacf(a, b, x):
    tiny, eps = 1e-30, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h

def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b

def t_sf2(t, df):
    if df <= 0:
        return float("nan")
    if t != t or t in (float("inf"), float("-inf")):
        return 0.0
    return betai(0.5 * df, 0.5, df / (df + t * t))

def t_ppf(p, df):
    if df <= 0:
        return float("nan")
    lo, hi = 0.0, 1.0
    while t_sf2(hi, df) > p and hi < 1e6:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_sf2(mid, df) > p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)

def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

def _gser(a, x):
    gln = math.lgamma(a)
    ap, s, d = a, 1.0 / a, 1.0 / a
    for _ in range(1000):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * 3e-16:
            break
    return s * math.exp(-x + a * math.log(x) - gln)

def _gcf(a, x):
    gln = math.lgamma(a)
    tiny = 1e-30
    b, c, d = x + 1.0 - a, 1.0 / tiny, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-16:
            break
    return math.exp(-x + a * math.log(x) - gln) * h

def chi2_sf(x, k):
    if x <= 0:
        return 1.0
    if k <= 0:
        return float("nan")
    a = 0.5 * k
    z = 0.5 * x
    return 1.0 - _gser(a, z) if z < a + 1.0 else _gcf(a, z)

def mean(v):
    return sum(v) / float(len(v)) if v else float("nan")

def median(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        return float("nan")
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

def sd(v):
    n = len(v)
    if n < 2:
        return float("nan")
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / float(n - 1))

def quantile(sorted_v, q):
    n = len(sorted_v)
    if n == 0:
        return float("nan")
    if n == 1:
        return float(sorted_v[0])
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_v[lo])
    return float(sorted_v[lo]) + (float(sorted_v[hi]) - float(sorted_v[lo])) * (pos - lo)

def skewness(v):
    n = len(v)
    if n < 3:
        return float("nan")
    m, s = mean(v), sd(v)
    if s == 0:
        return 0.0
    return sum(((x - m) / s) ** 3 for x in v) * n / float((n - 1) * (n - 2))

def kurtosis(v):
    n = len(v)
    if n < 4:
        return float("nan")
    m, s = mean(v), sd(v)
    if s == 0:
        return 0.0
    g2 = sum(((x - m) / s) ** 4 for x in v) * n * (n + 1) / float((n - 1) * (n - 2) * (n - 3))
    return g2 - 3.0 * (n - 1) ** 2 / float((n - 2) * (n - 3))

def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out

def tie_groups(v):
    counts = {}
    for x in v:
        counts[x] = counts.get(x, 0) + 1
    return [c for c in counts.values() if c > 1]

def descriptive(v, unit="-"):
    v = [float(x) for x in v]
    s = sorted(v)
    n = len(v)
    sdv = sd(v)
    return {
        "n": n, "unit": unit, "mean": mean(v), "sd": sdv,
        "se": (sdv / math.sqrt(n)) if n > 1 else float("nan"),
        "min": s[0] if n else float("nan"), "q1": quantile(s, 0.25), "median": quantile(s, 0.5),
        "q3": quantile(s, 0.75), "max": s[-1] if n else float("nan"),
        "iqr": (quantile(s, 0.75) - quantile(s, 0.25)) if n else float("nan"),
        "skewness": skewness(v), "excess_kurtosis": kurtosis(v),
        "mean_ci_95": [mean(v) - (t_ppf(0.05, n - 1) * sdv / math.sqrt(n)),
                       mean(v) + (t_ppf(0.05, n - 1) * sdv / math.sqrt(n))] if n > 1 and sdv == sdv else [],
    }

def student_t(a, b):
    n1, n2 = len(a), len(b)
    m1, m2 = mean(a), mean(b)
    s1, s2 = sd(a), sd(b)
    if n1 < 2 or n2 < 2 or s1 != s1 or s2 != s2:
        return {"ok": False, "reason": "a group has fewer than two observations or no spread"}
    df = n1 + n2 - 2
    sp2 = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / float(df)
    sp = math.sqrt(sp2)
    se = sp * math.sqrt(1.0 / n1 + 1.0 / n2)
    if se == 0:
        return {"ok": False, "reason": "both groups are constant, so the pooled standard error is 0"}
    diff = m1 - m2
    t = diff / se
    tt = t_ppf(0.05, df)
    d = diff / sp
    g = d * (1.0 - 3.0 / (4.0 * (n1 + n2) - 9.0)) if (n1 + n2) > 2 else d
    se_d = math.sqrt((n1 + n2) / float(n1 * n2) + d * d / (2.0 * (n1 + n2)))
    return {"ok": True, "test": "student_t", "design": "two_independent_groups",
            "n": [n1, n2], "df": df, "difference": diff,
            "ci_95": [diff - tt * se, diff + tt * se], "statistic_name": "t", "statistic": t,
            "p": t_sf2(t, df), "se_diff": se, "pooled_sd": sp,
            "effect_size": {"type": "cohen_d", "value": d,
                            "hedges_g": g, "ci_95": [d - Z95 * se_d, d + Z95 * se_d],
                            "ci_method": "analytic_large_sample",
                            "direction": "first level minus second level"}}

def _exact_mw_p(u, n1, n2):
    from itertools import combinations
    n = n1 + n2
    us = []
    for comb in combinations(range(n), n1):
        r = sum(c + 1 for c in comb) - n1 * (n1 + 1) / 2.0
        us.append(r)
    if not us:
        return float("nan")
    le = sum(1 for u2 in us if u2 <= u + 1e-9)
    ge = sum(1 for u2 in us if u2 >= u - 1e-9)
    return min(1.0, 2.0 * min(le, ge) / float(len(us)))

def mann_whitney_u(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return {"ok": False, "reason": "rank-sum needs at least three observations per group"}
    allv = list(a) + list(b)
    r = ranks(allv)
    r1 = sum(r[:n1])
    u1 = r1 - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    n = n1 + n2
    ties = tie_groups(allv)
    tie_corr = sum(t ** 3 - t for t in ties)
    mu = n1 * n2 / 2.0
    var = n1 * n2 / 12.0 * ((n + 1) - tie_corr / float(n * (n - 1))) if n > 1 else float("nan")
    if var and var > 0:
        z = (u1 - mu - 0.5 * (1 if u1 > mu else -1)) / math.sqrt(var)
        p_norm = min(1.0, 2.0 * (1.0 - norm_cdf(abs(z))))
    else:
        z, p_norm = float("nan"), float("nan")
    if not ties and n1 * n2 <= 60:
        p, method = _exact_mw_p(u, n1, n2), "exact_rank_enumeration"
    else:
        p, method = p_norm, "normal_approximation_with_tie_correction"
    rb = 1.0 - 2.0 * u / float(n1 * n2)
    point = median(a) - median(b)
    rnd = random.Random(SEED)
    boots = []
    for _ in range(1000):
        sa = [a[rnd.randrange(n1)] for _ in range(n1)]
        sb = [b[rnd.randrange(n2)] for _ in range(n2)]
        boots.append(sorted(sa)[len(sa) // 2] - sorted(sb)[len(sb) // 2])
    boots.sort()
    return {"ok": True, "test": "mann_whitney_u", "design": "two_independent_groups",
            "n": [n1, n2], "df": [], "statistic_name": "U", "statistic": u,
            "u1": u1, "u2": u2, "z": z, "p": p, "p_normal_approx": p_norm, "p_method": method,
            "difference": point, "median_difference_ci_95": [boots[24], boots[974]],
            "ci_method": "percentile_bootstrap", "ci_95": [boots[24], boots[974]],
            "effect_size": {"type": "rank_biserial", "value": rb, "ci_95": [],
                            "ci_method": "not applicable", "direction": "first level minus second"}}

def one_way_ranks(groups):
    sizes = [len(g) for g in groups]
    if min(sizes) < 3 or len(groups) < 3:
        return {"ok": False, "reason": "needs at least three groups with three observations each"}
    allv = [x for g in groups for x in g]
    n = len(allv)
    r = ranks(allv)
    idx, rsum, ssb, sst = 0, [], 0.0, 0.0
    rbar = (n + 1) / 2.0
    for g in groups:
        part = r[idx:idx + len(g)]
        idx += len(g)
        rsum.append(sum(part))
        ssb += len(g) * (mean(part) - rbar) ** 2
        sst += sum((x - rbar) ** 2 for x in part)
    ties = tie_groups(allv)
    corr = 1.0 - (sum(t ** 3 - t for t in ties) / float(n ** 3 - n)) if n > 1 else 1.0
    if corr <= 0:
        return {"ok": False, "reason": "the sample is one constant value, so ranks carry no information"}
    h = (n - 1) * ssb / sst if sst > 0 else 0.0
    df = len(groups) - 1
    eps2 = ssb / sst if sst > 0 else 0.0
    rnd = random.Random(SEED)
    boots = []
    pooled = []
    for g in groups:
        pooled.append([x for x in g])
    for _ in range(1000):
        picks = []
        for g in pooled:
            picks.append([g[rnd.randrange(len(g))] for _ in range(len(g))])
        rr = ranks([x for g in picks for x in g])
        i2, ssb2, sst2, rb2 = 0, 0.0, 0.0, (n + 1) / 2.0
        for g in picks:
            part = rr[i2:i2 + len(g)]
            i2 += len(g)
            ssb2 += len(g) * (mean(part) - rb2) ** 2
            sst2 += sum((x - rb2) ** 2 for x in part)
        boots.append(ssb2 / sst2 if sst2 > 0 else 0.0)
    boots.sort()
    return {"ok": True, "test": "kruskal_wallis", "design": "multi_group", "n": sizes, "df": df,
            "statistic_name": "H", "statistic": h, "p": chi2_sf(h, df),
            "epsilon_squared": eps2, "tie_correction": corr, "group_rank_sums": rsum,
            "ci_95": [boots[24], boots[974]], "ci_method": "percentile_bootstrap",
            "effect_size": {"type": "epsilon_squared", "value": eps2,
                            "ci_95": [boots[24], boots[974]], "ci_method": "percentile_bootstrap",
                            "direction": "between-group share of ranked variance"}}

def one_way_anova(groups):
    k = len(groups)
    if k < 3 or min(len(g) for g in groups) < 2:
        return {"ok": False, "reason": "needs at least three groups with two observations each"}
    n = sum(len(g) for g in groups)
    grand = mean([x for g in groups for x in g])
    ssb = sum(len(g) * (mean(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - mean(g)) ** 2 for x in g) for g in groups)
    df1, df2 = k - 1, n - k
    if ssw <= 0:
        return {"ok": False, "reason": "every group is constant, so the residual variance is 0"}
    f = (ssb / float(df1)) / (ssw / float(df2))
    eta2 = ssb / (ssb + ssw)
    return {"ok": True, "test": "one_way_anova", "design": "multi_group", "n": [len(g) for g in groups],
            "df": [df1, df2], "statistic_name": "F", "statistic": f, "p": f_sf(f, df1, df2),
            "eta_squared": eta2, "ci_95": [], "ci_method": "not applicable",
            "effect_size": {"type": "eta_squared", "value": eta2, "ci_95": [],
                            "ci_method": "not applicable",
                            "direction": "between-group share of variance"}}

def paired_t(diffs):
    d = [x for x in diffs if x == x]
    n = len(d)
    if n < 2:
        return {"ok": False, "reason": "fewer than two paired differences"}
    m, sdd = mean(d), sd(d)
    if sdd != sdd or sdd == 0:
        return {"ok": False, "reason": "the paired differences do not vary"}
    se = sdd / math.sqrt(n)
    t = m / se
    tt = t_ppf(0.05, n - 1)
    return {"ok": True, "test": "paired_t", "design": "paired", "n": [n], "df": n - 1,
            "statistic_name": "t", "statistic": t, "p": t_sf2(t, n - 1), "difference": m,
            "ci_95": [m - tt * se, m + tt * se], "ci_method": "analytic_large_sample",
            "effect_size": {"type": "cohen_dz", "value": m / sdd, "ci_95": [],
                            "ci_method": "not applicable", "direction": "mean paired difference"}}

def _exact_wilcoxon_p(w, n):
    from itertools import combinations
    if n > 20:
        return float("nan")
    le = ge = 0
    tot = 0
    for k in range(n + 1):
        for comb in combinations(range(1, n + 1), k):
            tot += 1
            s = sum(comb)
            if s <= w + 1e-9:
                le += 1
            if s >= w - 1e-9:
                ge += 1
    return min(1.0, 2.0 * min(le, ge) / float(tot))

def wilcoxon_signed_rank(diffs):
    d = [x for x in diffs if x == x]
    zeros = sum(1 for x in d if x == 0)
    d = [x for x in d if x != 0]
    n = len(d)
    if n < 2:
        return {"ok": False, "reason": "fewer than two non-zero paired differences"}
    r = ranks([abs(x) for x in d])
    wp = sum(rr for rr, x in zip(r, d) if x > 0)
    wm = sum(rr for rr, x in zip(r, d) if x < 0)
    w = min(wp, wm)
    mu = n * (n + 1) / 4.0
    ties = tie_groups([abs(x) for x in d])
    var = n * (n + 1) * (2 * n + 1) / 24.0 - sum(t ** 3 - t for t in ties) / 48.0
    if var > 0:
        z = (w - mu + 0.5 * (1 if w > mu else -1)) / math.sqrt(var)
        p_norm = min(1.0, 2.0 * (1.0 - norm_cdf(abs(z))))
    else:
        z, p_norm = float("nan"), float("nan")
    if not ties and n <= 20:
        p, method = _exact_wilcoxon_p(w, n), "exact_sign_enumeration"
    else:
        p, method = p_norm, "normal_approximation_with_tie_correction"
    sdd = sd(d)
    dz = mean(d) / sdd if sdd and sdd == sdd else float("nan")
    point = median(d)
    rnd = random.Random(SEED)
    boots = []
    for _ in range(1000):
        s = sorted(d[rnd.randrange(n)] for _ in range(n))
        boots.append(s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2.0)
    boots.sort()
    return {"ok": True, "test": "wilcoxon_signed_rank", "design": "paired", "n": [n], "pairs": len(diffs),
            "zeros_dropped": zeros, "df": [], "statistic_name": "W", "statistic": w,
            "w_positive": wp, "w_negative": wm, "z": z, "p": p, "p_normal_approx": p_norm,
            "p_method": method, "difference": point,
            "ci_95": [boots[24], boots[974]], "median_difference_ci_95": [boots[24], boots[974]],
            "ci_method": "percentile_bootstrap",
            "effect_size": {"type": "cohen_dz", "value": dz, "ci_95": [],
                            "ci_method": "not applicable", "direction": "mean paired difference"}}

def _pearson_core(x, y):
    n = len(x)
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return n, mx, my, sxy, sxx, syy

def pearson_r(x, y):
    core = _pearson_core(x, y)
    if not core:
        return {"ok": False, "reason": "one of the two variables is constant"}
    n, mx, my, sxy, sxx, syy = core
    r = sxy / math.sqrt(sxx * syy)
    r = max(-1.0, min(1.0, r))
    if abs(r) >= 1.0:
        return {"ok": True, "test": "pearson_r", "n": [n], "df": n - 2, "statistic_name": "r",
                "statistic": r, "p": 0.0, "r_squared": r * r,
                "ci_95": [r, r], "ci_method": "fisher_z",
                "effect_size": {"type": "r_squared", "value": r * r, "ci_95": [r * r, r * r],
                                "ci_method": "fisher_z", "direction": "positive association"}}
    t = r * math.sqrt((n - 2) / (1.0 - r * r))
    z = math.atanh(r)
    se = 1.0 / math.sqrt(n - 3.0) if n > 3 else float("nan")
    ci = [math.tanh(z - Z95 * se), math.tanh(z + Z95 * se)] if se == se else []
    sq = [max(0.0, ci[0]) ** 2, max(0.0, ci[1]) ** 2] if ci else []
    return {"ok": True, "test": "pearson_r", "design": "correlation", "n": [n], "df": n - 2,
            "statistic_name": "r", "statistic": r, "p": t_sf2(t, n - 2), "r_squared": r * r,
            "ci_95": ci, "ci_method": "fisher_z",
            "effect_size": {"type": "r_squared", "value": r * r, "ci_95": sq,
                            "ci_method": "fisher_z_squared", "direction": "positive association"}}

def spearman_rho(x, y):
    n = len(x)
    if n < 4:
        return {"ok": False, "reason": "a rank correlation needs at least four pairs"}
    rx, ry = ranks(x), ranks(y)
    core = _pearson_core(rx, ry)
    if not core:
        return {"ok": False, "reason": "one variable never changes rank, so the correlation is undefined"}
    rho = core[3] / math.sqrt(core[4] * core[5])
    rho = max(-1.0, min(1.0, rho))
    if abs(rho) >= 1.0:
        p = 0.0
    else:
        t = rho * math.sqrt((n - 2) / (1.0 - rho * rho))
        p = t_sf2(t, n - 2)
    z = math.atanh(rho * 0.999999)
    se = 1.0 / math.sqrt(n - 3.0) if n > 3 else float("nan")
    ci = [math.tanh(z - Z95 * se), math.tanh(z + Z95 * se)] if se == se else []
    sq = [max(0.0, ci[0]) ** 2, max(0.0, ci[1]) ** 2] if ci else []
    return {"ok": True, "test": "spearman_rho", "design": "correlation", "n": [n], "df": n - 2,
            "statistic_name": "rho", "statistic": rho, "p": p, "r_squared": rho * rho,
            "ci_95": ci, "ci_method": "fisher_z", "tie_groups": len(tie_groups(list(x) + list(y))),
            "effect_size": {"type": "r_squared", "value": rho * rho, "ci_95": sq,
                            "ci_method": "fisher_z_squared", "direction": "positive rank association"}}

def ols_slope(x, y):
    core = _pearson_core(x, y)
    if not core:
        return {"ok": False, "reason": "the predictor is constant, so no slope can be estimated"}
    n, mx, my, sxy, sxx, syy = core
    if sxx <= 0 or n < 4:
        return {"ok": False, "reason": "a regression needs at least four pairs and a varying predictor"}
    slope = sxy / sxx
    intercept = my - slope * mx
    rss = syy - slope * sxy
    if rss <= 0:
        return {"ok": True, "test": "ols_slope", "design": "regression", "n": [n], "df": n - 2,
                "statistic_name": "slope", "statistic": slope, "intercept": intercept, "p": 0.0,
                "r_squared": 1.0, "residual_sd": 0.0, "ci_95": [slope, slope],
                "ci_method": "analytic_large_sample", "note": "the points fall on a line",
                "effect_size": {"type": "r_squared", "value": 1.0, "ci_95": [1.0, 1.0],
                                "ci_method": "analytic_large_sample", "direction": "per unit of x"}}
    s2 = rss / float(n - 2)
    se = math.sqrt(s2 / sxx)
    t = slope / se
    tt = t_ppf(0.05, n - 2)
    r2 = 1.0 - rss / syy if syy > 0 else float("nan")
    return {"ok": True, "test": "ols_slope", "design": "regression", "n": [n], "df": n - 2,
            "statistic_name": "slope", "statistic": slope, "intercept": intercept, "se_slope": se,
            "p": t_sf2(t, n - 2), "r_squared": r2, "residual_sd": math.sqrt(s2),
            "ci_95": [slope - tt * se, slope + tt * se], "ci_method": "analytic_large_sample",
            "effect_size": {"type": "r_squared", "value": r2, "ci_95": [],
                            "ci_method": "analytic_large_sample", "direction": "per unit of x"}}

def f_sf(x, d1, d2):
    if x <= 0:
        return 1.0
    if d1 <= 0 or d2 <= 0:
        return float("nan")
    return betai(0.5 * d2, 0.5 * d1, d2 / (d2 + d1 * x))

def jarque_bera(v):
    v = [float(x) for x in v]
    n = len(v)
    if n < 8:
        return {"test": "jarque_bera", "statistic": float("nan"), "p": float("nan"),
                "verdict": "not_tested", "reason": "fewer than eight observations"}
    m = mean(v)
    s = sd(v)
    if s == 0:
        return {"test": "jarque_bera", "statistic": float("nan"), "p": float("nan"),
                "verdict": "not_tested", "reason": "the sample is constant"}
    b1 = sum(((x - m) / s) ** 3 for x in v) / float(n)
    b2 = sum(((x - m) / s) ** 4 for x in v) / float(n)
    jb = n / 6.0 * (b1 * b1 + (b2 - 3.0) ** 2 / 4.0)
    p = chi2_sf(jb, 2)
    return {"test": "jarque_bera", "statistic": jb, "p": p,
            "verdict": "pass" if p > 0.05 else "fail",
            "note": "moment skewness %.4f, moment kurtosis %.4f" % (b1, b2)}

def brown_forsythe(groups):
    k = len(groups)
    ns = [len(g) for g in groups]
    if k < 2 or min(ns) < 2:
        return {"test": "brown_forsythe", "statistic": float("nan"), "p": float("nan"),
                "verdict": "not_tested", "reason": "a group has fewer than two observations"}
    z = [[abs(x - quantile(sorted(g), 0.5)) for x in g] for g in groups]
    n = sum(ns)
    zbar = mean([x for g in z for x in g])
    num = sum(len(g) * (mean(g) - zbar) ** 2 for g in z)
    den = sum(sum((x - mean(g)) ** 2 for x in g) for g in z)
    if den == 0:
        return {"test": "brown_forsythe", "statistic": float("nan"), "p": float("nan"),
                "verdict": "not_tested", "reason": "every deviation is 0, so the spread is equal by construction"}
    df1, df2 = k - 1, n - k
    w = ((n - k) / float(k - 1)) * num / den
    p = f_sf(w, df1, df2)
    return {"test": "brown_forsythe", "statistic": w, "p": p, "df": [df1, df2],
            "verdict": "pass" if p > 0.05 else "fail"}

def holm(pvals):
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    adj = [1.0] * m
    run = 0.0
    for rank, i in enumerate(idx):
        val = min(1.0, (m - rank) * pvals[i])
        run = max(run, val)
        adj[i] = run
    return adj

def fmt(x, digits=4, dash="-"):
    if x is None or x != x:
        return dash
    if x in (float("inf"), float("-inf")):
        return "inf" if x > 0 else "-inf"
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return ("%%.%dg" % digits) % x

def _log_fact(n):
    return math.lgamma(n + 1.0)

def fisher_exact(table):
    if len(table) != 2 or any(len(r) != 2 for r in table):
        return {"ok": False, "reason": "Fisher exact needs a 2x2 table"}
    (a, b), (c, d) = table
    n = a + b + c + d
    r1, c1 = a + b, a + c
    if n == 0 or r1 == 0 or c1 == 0:
        return {"ok": False, "reason": "a table margin is empty, so the test is degenerate"}

    def hyper(x):
        return math.exp(_log_fact(r1) + _log_fact(n - r1) + _log_fact(c1) + _log_fact(n - c1)
                        - _log_fact(n) - _log_fact(x) - _log_fact(r1 - x)
                        - _log_fact(c1 - x) - _log_fact(n - r1 - c1 + x))

    p_obs = hyper(a)
    lo, hi = max(0, c1 - (n - r1)), min(r1, c1)
    p_two = sum(hyper(x) for x in range(lo, hi + 1) if hyper(x) <= p_obs * (1 + 1e-9))
    p_two = min(1.0, p_two)
    if b == 0 or c == 0 or a == 0 or d == 0:
        orat = float("inf") if b * c == 0 and a * d > 0 else float("nan")
        ci = []
    else:
        orat = (a * d) / float(b * c)
        se = math.sqrt(1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d)
        ci = [orat * math.exp(-Z95 * se), orat * math.exp(Z95 * se)]
    phi2 = (a * d - b * c) ** 2 * n / float(r1 * (n - r1) * c1 * (n - c1)) if n > 0 else float("nan")
    v = math.sqrt(phi2 / n) if phi2 == phi2 and n > 0 else float("nan")
    return {"ok": True, "test": "fisher_exact", "design": "contingency", "n": [n], "df": 1,
            "statistic_name": "odds_ratio", "statistic": orat, "p": p_two,
            "table": [[a, b], [c, d]], "expected_min": min(r1 * c1 / float(n), r1 * (n - c1) / float(n),
                                                             (n - r1) * c1 / float(n),
                                                             (n - r1) * (n - c1) / float(n)),
            "ci_95": ci, "ci_method": "log_or_woolf", "cramers_v": v,
            "effect_size": {"type": "odds_ratio", "value": orat, "ci_95": ci,
                            "ci_method": "log_or_woolf", "direction": "row 1 against row 2"}}
