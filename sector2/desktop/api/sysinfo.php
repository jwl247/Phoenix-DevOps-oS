<?php
/**
 * sysinfo.php — Phoenix System Telemetry API
 * Returns CPU %, RAM %, Swap %, and security threat level.
 * Runs on phoenix-ext (Apache/www-data).
 *
 * GET /desktop/api/sysinfo.php
 *
 * Security threat level (1-5):
 *   1 = clear   — no anomalies
 *   2 = low     — minor activity (few failed logins)
 *   3 = elevated — notable activity (repeated failures, high load)
 *   4 = high    — active threat indicators
 *   5 = critical — confirmed breach indicators
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */

header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

// ── CPU % ────────────────────────────────────────────────────────────────
function get_cpu_pct(): float {
    // Read /proc/stat twice, 200ms apart — calculate delta
    $read = function(): array {
        $line = file('/proc/stat')[0] ?? '';
        $p = preg_split('/\s+/', trim($line));
        return [(int)$p[1]+(int)$p[2]+(int)$p[3], (int)$p[4], array_sum(array_slice($p,1))];
    };
    [$u1, $i1, $t1] = $read();
    usleep(200000);  // 200ms
    [$u2, $i2, $t2] = $read();
    $dt = $t2 - $t1;
    if ($dt <= 0) return 0.0;
    $idle_delta = $i2 - $i1;
    return round((1 - $idle_delta / $dt) * 100, 1);
}

// ── RAM / Swap ────────────────────────────────────────────────────────────
function get_mem(): array {
    $meminfo = [];
    foreach (file('/proc/meminfo') as $line) {
        [$key, $val] = explode(':', $line, 2);
        $meminfo[trim($key)] = (int)trim($val);  // kB
    }
    $total      = $meminfo['MemTotal']     ?? 0;
    $available  = $meminfo['MemAvailable'] ?? 0;
    $swap_total = $meminfo['SwapTotal']    ?? 0;
    $swap_free  = $meminfo['SwapFree']     ?? 0;

    $ram_used_pct  = $total > 0 ? round(($total - $available) / $total * 100, 1) : 0.0;
    $swap_used_pct = $swap_total > 0 ? round(($swap_total - $swap_free) / $swap_total * 100, 1) : 0.0;

    return [
        'ram_total_mb'  => round($total / 1024),
        'ram_used_mb'   => round(($total - $available) / 1024),
        'ram_pct'       => $ram_used_pct,
        'swap_total_mb' => round($swap_total / 1024),
        'swap_used_mb'  => round(($swap_total - $swap_free) / 1024),
        'swap_pct'      => $swap_used_pct,
    ];
}

// ── Security threat level ─────────────────────────────────────────────────
function get_threat_level(): array {
    $level  = 1;
    $detail = [];

    // 1. Failed SSH logins in last 10 minutes
    $auth_log = '/var/log/auth.log';
    $failed   = 0;
    if (is_readable($auth_log)) {
        $lines = shell_exec("grep -c 'Failed password' " . escapeshellarg($auth_log) . " 2>/dev/null || echo 0");
        $failed = (int)trim($lines ?? '0');
        // Recent failures (last 10 min)
        $recent = shell_exec("awk 'NR==1{cmd=\"date -d '\"'\"'\" $1 \" \" $2 \" \" $3 \"'\"'\"' +%s 2>/dev/null\"; cmd | getline t; close(cmd); start=systime()-600} t>=start && /Failed password/{c++} END{print c+0}' " . escapeshellarg($auth_log) . " 2>/dev/null");
        $recent_fail = (int)trim($recent ?? '0');
        if ($recent_fail > 20)      { $level = max($level, 4); $detail[] = "$recent_fail SSH fails (10m)"; }
        elseif ($recent_fail > 5)   { $level = max($level, 3); $detail[] = "$recent_fail SSH fails (10m)"; }
        elseif ($recent_fail > 0)   { $level = max($level, 2); $detail[] = "$recent_fail SSH fails (10m)"; }
    }

    // 2. System load average vs CPU count
    $loadavg = sys_getloadavg();
    $load1   = $loadavg[0] ?? 0;
    $cpus    = (int)(shell_exec('nproc') ?? 1);
    $load_ratio = $cpus > 0 ? $load1 / $cpus : 0;
    if ($load_ratio > 2.0)      { $level = max($level, 3); $detail[] = sprintf('load %.1f (%dx CPUs)', $load1, $cpus); }
    elseif ($load_ratio > 1.0)  { $level = max($level, 2); $detail[] = sprintf('load %.1f', $load1); }

    // 3. Check for zombie processes (sign of runaway spawning)
    $zombies = (int)trim(shell_exec("ps aux | awk '\$8==\"Z\"{c++}END{print c+0}' 2>/dev/null") ?? '0');
    if ($zombies > 10) { $level = max($level, 3); $detail[] = "$zombies zombies"; }
    elseif ($zombies > 3) { $level = max($level, 2); $detail[] = "$zombies zombies"; }

    // 4. Check /var/log/phoenix/audit.log for 'deny' events in last 5 min
    $phoenix_log = '/var/log/phoenix/audit.log';
    if (is_readable($phoenix_log)) {
        $five_ago  = date('c', time() - 300);
        $denies    = 0;
        $handle    = fopen($phoenix_log, 'r');
        if ($handle) {
            // Read last 200 lines efficiently
            fseek($handle, 0, SEEK_END);
            $size = ftell($handle);
            $read = min($size, 16384);
            fseek($handle, -$read, SEEK_END);
            $chunk = fread($handle, $read);
            fclose($handle);
            $lines_check = array_slice(explode("\n", $chunk), -200);
            foreach ($lines_check as $ln) {
                if (str_contains($ln, '"result":"denied"') || str_contains($ln, '"result":"deny"')) {
                    $denies++;
                }
            }
        }
        if ($denies > 5) { $level = max($level, 3); $detail[] = "$denies Phoenix denies (5m)"; }
    }

    $labels = [1=>'CLEAR', 2=>'LOW', 3=>'ELEVATED', 4=>'HIGH', 5=>'CRITICAL'];
    return [
        'level'   => $level,
        'label'   => $labels[$level],
        'detail'  => $detail,
        'load1'   => round($load1, 2),
        'load5'   => round($loadavg[1] ?? 0, 2),
        'load15'  => round($loadavg[2] ?? 0, 2),
    ];
}

// ── Response ──────────────────────────────────────────────────────────────
$mem     = get_mem();
$threat  = get_threat_level();
$cpu_pct = get_cpu_pct();

echo json_encode([
    'ok'      => true,
    'ts'      => date('c'),
    'cpu_pct' => $cpu_pct,
    'memory'  => $mem,
    'threat'  => $threat,
]);
