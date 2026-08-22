<?php

declare(strict_types=1);

/*
 * Nagios status.dat Prometheus exporter.
 *
 * Cardinality policy:
 *
 *   Host metrics:
 *     - Static metric names.
 *     - Only the "host" label.
 *
 *   Service metrics:
 *     - Static base metric names.
 *     - Only "host" and "service" labels.
 *
 *   Service performance data:
 *     - Explicit allowlist only.
 *     - Each perfdata key maps to a static Prometheus metric name.
 *     - No arbitrary "metric" label.
 *     - Thresholds are intentionally ignored.
 *
 *   Program metrics:
 *     - Fixed-cardinality metrics from programstatus.
 *     - Rolling counters use only the bounded 1m/5m/15m window label.
 */

$statusFile = '/var/lib/nagios4/status.dat';

/*
 * Explicit allowlist for service performance data.
 *
 * Adding a perfdata key here deliberately creates one additional possible
 * metric series per service that exposes that key.
 *
 * unit:
 *   raw      - Export unchanged.
 *   seconds  - Convert Nagios time UOM to seconds.
 *   bytes    - Convert byte UOM to bytes.
 *   percent  - Export as Nagios percentage value (0..100).
 */
$servicePerfDataAllowList = [
    'load1' => [
        'metric' => 'nagios_service_perfdata_load1',
        'help' => 'Nagios service 1 minute load average.',
        'unit' => 'raw',
    ],
    'load5' => [
        'metric' => 'nagios_service_perfdata_load5',
        'help' => 'Nagios service 5 minute load average.',
        'unit' => 'raw',
    ],
    'load15' => [
        'metric' => 'nagios_service_perfdata_load15',
        'help' => 'Nagios service 15 minute load average.',
        'unit' => 'raw',
    ],
    'users' => [
        'metric' => 'nagios_service_perfdata_users',
        'help' => 'Number of users reported by the Nagios service.',
        'unit' => 'raw',
    ],
    'time' => [
        'metric' => 'nagios_service_perfdata_time_seconds',
        'help' => 'Response or execution time reported by the Nagios service.',
        'unit' => 'seconds',
    ],
    'size' => [
        'metric' => 'nagios_service_perfdata_size_bytes',
        'help' => 'Size reported by the Nagios service in bytes.',
        'unit' => 'bytes',
    ],
    'rta' => [
        'metric' => 'nagios_service_perfdata_rta_seconds',
        'help' => 'Round-trip average reported by the Nagios service.',
        'unit' => 'seconds',
    ],
    'pl' => [
        'metric' => 'nagios_service_perfdata_packet_loss_percent',
        'help' => 'Packet loss percentage reported by the Nagios service.',
        'unit' => 'percent',
    ],
    'procs' => [
        'metric' => 'nagios_service_perfdata_processes',
        'help' => 'Process count reported by the Nagios service.',
        'unit' => 'raw',
    ],
];

header('Content-Type: text/plain; version=0.0.4; charset=utf-8');

$families = [];

/**
 * Escape a Prometheus label value.
 */
function label_escape(string $value): string
{
    return str_replace(
        ["\\", "\n", '"'],
        ["\\\\", "\\n", '\\"'],
        $value
    );
}

/**
 * Add one sample to a Prometheus metric family.
 *
 * @param array<string, mixed> $families
 * @param array<string, string> $labels
 */
function add_metric(
    array &$families,
    string $name,
    string $help,
    string $type,
    array $labels,
    mixed $value
): void {
    if ($value === null || $value === '' || !is_numeric($value)) {
        return;
    }

    $labelParts = [];

    foreach ($labels as $labelName => $labelValue) {
        $labelParts[] = sprintf(
            '%s="%s"',
            $labelName,
            label_escape((string) $labelValue)
        );
    }

    $labelText = $labelParts === []
        ? ''
        : '{' . implode(',', $labelParts) . '}';

    if (!isset($families[$name])) {
        $families[$name] = [
            'help' => $help,
            'type' => $type,
            'lines' => [],
        ];
    }

    $families[$name]['lines'][] = sprintf(
        '%s%s %s',
        $name,
        $labelText,
        (string) (float) $value
    );
}

/**
 * Output all Prometheus metric families.
 *
 * @param array<string, mixed> $families
 */
function flush_metrics(array $families): void
{
    ksort($families);

    foreach ($families as $name => $family) {
        echo "# HELP {$name} {$family['help']}\n";
        echo "# TYPE {$name} {$family['type']}\n";

        foreach ($family['lines'] as $line) {
            echo $line . "\n";
        }
    }
}

/**
 * Parse relevant status.dat blocks.
 *
 * @return array<int, array{0: string, 1: array<string, string>}>
 */
function parse_status_dat(string $file): array
{
    if (!is_readable($file)) {
        throw new RuntimeException(
            "Cannot read Nagios status file: {$file}"
        );
    }

    $handle = fopen($file, 'r');

    if ($handle === false) {
        throw new RuntimeException(
            "Cannot open Nagios status file: {$file}"
        );
    }

    $blocks = [];
    $blockType = null;
    $blockData = [];

    $allowedBlockTypes = [
        'programstatus',
        'hoststatus',
        'servicestatus',
    ];

    try {
        while (($line = fgets($handle)) !== false) {
            $line = trim($line);

            if ($line === '') {
                continue;
            }

            if (str_ends_with($line, '{')) {
                $candidate = trim(substr($line, 0, -1));

                if (in_array($candidate, $allowedBlockTypes, true)) {
                    $blockType = $candidate;
                    $blockData = [];
                } else {
                    $blockType = null;
                    $blockData = [];
                }

                continue;
            }

            if ($line === '}') {
                if ($blockType !== null) {
                    $blocks[] = [$blockType, $blockData];
                }

                $blockType = null;
                $blockData = [];

                continue;
            }

            if ($blockType !== null && str_contains($line, '=')) {
                [$key, $value] = explode('=', $line, 2);

                $blockData[trim($key)] = trim($value);
            }
        }
    } finally {
        fclose($handle);
    }

    return $blocks;
}

/**
 * Parse Nagios plugin performance_data values.
 *
 * Thresholds following the value/UOM are intentionally ignored.
 *
 * Examples:
 *
 *   rta=0.154000ms;5000;5000;0
 *   pl=0%;100;100;0;
 *   load1=0.180;8;12;0;
 *   time=0.000612s;;;0;10
 *   size=559B;;;0;
 *
 * @return array<string, array{value: float, uom: string}>
 */
function parse_performance_data(string $performanceData): array
{
    if ($performanceData === '') {
        return [];
    }

    $pattern = "/(?:'((?:''|[^'])*)'|([^\\s=]+))="
        . "([-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)"
        . "(?:[eE][-+]?\\d+)?)"
        . "([A-Za-z%]*)/";

    $matchCount = preg_match_all(
        $pattern,
        $performanceData,
        $matches,
        PREG_SET_ORDER
    );

    if ($matchCount === false || $matchCount === 0) {
        return [];
    }

    $parsed = [];

    foreach ($matches as $match) {
        $label = $match[1] !== ''
            ? str_replace("''", "'", $match[1])
            : $match[2];

        $parsed[$label] = [
            'value' => (float) $match[3],
            'uom' => $match[4] ?? '',
        ];
    }

    return $parsed;
}

/**
 * Convert Nagios perfdata UOM to the unit expected by Prometheus.
 */
function convert_perfdata_value(
    float $value,
    string $uom,
    string $targetUnit
): ?float {
    if ($targetUnit === 'raw') {
        return $value;
    }

    if ($targetUnit === 'percent') {
        return $uom === '%' || $uom === ''
            ? $value
            : null;
    }

    if ($targetUnit === 'seconds') {
        return match ($uom) {
            's', '' => $value,
            'ms' => $value / 1000,
            'us' => $value / 1000000,
            default => null,
        };
    }

    if ($targetUnit === 'bytes') {
        return match ($uom) {
            'B', '' => $value,
            'KB' => $value * 1024,
            'MB' => $value * 1024 * 1024,
            'GB' => $value * 1024 * 1024 * 1024,
            'TB' => $value * 1024 * 1024 * 1024 * 1024,
            default => null,
        };
    }

    return null;
}

/**
 * Emit known static host metrics.
 *
 * @param array<string, mixed> $families
 * @param array<string, string> $data
 */
function emit_host_metrics(
    array &$families,
    array $data
): void {
    $labels = [
        'host' => $data['host_name'] ?? 'unknown',
    ];

    add_metric(
        $families,
        'nagios_host_state',
        'Nagios host state: 0=UP, 1=DOWN, 2=UNREACHABLE.',
        'gauge',
        $labels,
        $data['current_state'] ?? null
    );

    add_metric(
        $families,
        'nagios_host_state_type',
        'Nagios host state type: 0=SOFT, 1=HARD.',
        'gauge',
        $labels,
        $data['state_type'] ?? null
    );

    add_metric(
        $families,
        'nagios_host_check_latency_seconds',
        'Nagios host check latency in seconds.',
        'gauge',
        $labels,
        $data['check_latency'] ?? null
    );

    add_metric(
        $families,
        'nagios_host_execution_time_seconds',
        'Nagios host check execution time in seconds.',
        'gauge',
        $labels,
        $data['check_execution_time']
            ?? $data['execution_time']
            ?? null
    );

    $suppressed = (
        (int) ($data['scheduled_downtime_depth'] ?? 0) > 0
        || (int) ($data['problem_has_been_acknowledged'] ?? 0) > 0
    ) ? 1 : 0;

    add_metric(
        $families,
        'nagios_host_problem_suppressed',
        'Whether the Nagios host problem is acknowledged or in downtime.',
        'gauge',
        $labels,
        $suppressed
    );

    add_metric(
        $families,
        'nagios_host_is_flapping',
        'Whether the Nagios host is currently flapping.',
        'gauge',
        $labels,
        $data['is_flapping'] ?? null
    );

    /*
     * Host ping performance data is deliberately static rather than
     * dynamically exposing arbitrary plugin perfdata names.
     */
    $perfdata = parse_performance_data(
        $data['performance_data'] ?? ''
    );

    if (isset($perfdata['rta'])) {
        $rta = convert_perfdata_value(
            $perfdata['rta']['value'],
            $perfdata['rta']['uom'],
            'seconds'
        );

        add_metric(
            $families,
            'nagios_host_ping_rta_seconds',
            'Nagios host ping round-trip average in seconds.',
            'gauge',
            $labels,
            $rta
        );
    }

    if (isset($perfdata['pl'])) {
        $packetLoss = convert_perfdata_value(
            $perfdata['pl']['value'],
            $perfdata['pl']['uom'],
            'percent'
        );

        add_metric(
            $families,
            'nagios_host_ping_packet_loss_percent',
            'Nagios host ping packet loss percentage.',
            'gauge',
            $labels,
            $packetLoss
        );
    }
}

/**
 * Emit base service metrics plus explicitly allowlisted performance data.
 *
 * @param array<string, mixed> $families
 * @param array<string, string> $data
 * @param array<string, array<string, string>> $perfdataAllowList
 */
function emit_service_metrics(
    array &$families,
    array $data,
    array $perfdataAllowList
): void {
    $labels = [
        'host' => $data['host_name'] ?? 'unknown',
        'service' => $data['service_description'] ?? 'unknown',
    ];

    add_metric(
        $families,
        'nagios_service_state',
        'Nagios service state: 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN.',
        'gauge',
        $labels,
        $data['current_state'] ?? null
    );

    add_metric(
        $families,
        'nagios_service_state_type',
        'Nagios service state type: 0=SOFT, 1=HARD.',
        'gauge',
        $labels,
        $data['state_type'] ?? null
    );

    add_metric(
        $families,
        'nagios_service_problem_acknowledged',
        'Whether the Nagios service problem is acknowledged.',
        'gauge',
        $labels,
        $data['problem_has_been_acknowledged'] ?? null
    );

    add_metric(
        $families,
        'nagios_service_check_latency_seconds',
        'Nagios service check latency in seconds.',
        'gauge',
        $labels,
        $data['check_latency'] ?? null
    );

    add_metric(
        $families,
        'nagios_service_check_execution_seconds',
        'Nagios service check execution time in seconds.',
        'gauge',
        $labels,
        $data['check_execution_time']
            ?? $data['execution_time']
            ?? null
    );

    add_metric(
        $families,
        'nagios_service_check_last_state_change',
        'Unix timestamp of the last Nagios service state change.',
        'gauge',
        $labels,
        $data['last_state_change'] ?? null
    );

    $perfdata = parse_performance_data(
        $data['performance_data'] ?? ''
    );

    foreach ($perfdataAllowList as $perfdataName => $definition) {
        /*
         * Missing perfdata values are intentionally ignored. This ensures
         * only service/metric combinations actually reported by Nagios
         * produce Prometheus time series.
         */
        if (!isset($perfdata[$perfdataName])) {
            continue;
        }

        $convertedValue = convert_perfdata_value(
            $perfdata[$perfdataName]['value'],
            $perfdata[$perfdataName]['uom'],
            $definition['unit']
        );

        if ($convertedValue === null) {
            continue;
        }

        add_metric(
            $families,
            $definition['metric'],
            $definition['help'],
            'gauge',
            $labels,
            $convertedValue
        );
    }
}

/**
 * Emit one Nagios 1/5/15 minute statistics tuple.
 *
 * @param array<string, mixed> $families
 */
function emit_program_window_metric(
    array &$families,
    string $rawValue,
    string $metricName,
    string $help
): void {
    $values = explode(',', $rawValue);

    if (count($values) !== 3) {
        return;
    }

    foreach (
        [
            '1m' => $values[0],
            '5m' => $values[1],
            '15m' => $values[2],
        ] as $window => $value
    ) {
        add_metric(
            $families,
            $metricName,
            $help,
            'gauge',
            ['window' => $window],
            trim($value)
        );
    }
}

/**
 * Emit selected fixed-cardinality programstatus metrics.
 *
 * @param array<string, mixed> $families
 * @param array<string, string> $data
 */
function emit_program_metrics(
    array &$families,
    array $data
): void {
    add_metric(
        $families,
        'nagios_program_start_time_seconds',
        'Unix timestamp when the Nagios process started.',
        'gauge',
        [],
        $data['program_start'] ?? null
    );

    $booleanMetrics = [
        'enable_notifications' => [
            'nagios_program_notifications_enabled',
            'Whether Nagios notifications are enabled.',
        ],
        'active_service_checks_enabled' => [
            'nagios_program_active_service_checks_enabled',
            'Whether active Nagios service checks are enabled.',
        ],
        'passive_service_checks_enabled' => [
            'nagios_program_passive_service_checks_enabled',
            'Whether passive Nagios service checks are enabled.',
        ],
        'active_host_checks_enabled' => [
            'nagios_program_active_host_checks_enabled',
            'Whether active Nagios host checks are enabled.',
        ],
        'passive_host_checks_enabled' => [
            'nagios_program_passive_host_checks_enabled',
            'Whether passive Nagios host checks are enabled.',
        ],
        'enable_event_handlers' => [
            'nagios_program_event_handlers_enabled',
            'Whether Nagios event handlers are enabled.',
        ],
        'enable_flap_detection' => [
            'nagios_program_flap_detection_enabled',
            'Whether Nagios flap detection is enabled.',
        ],
        'check_service_freshness' => [
            'nagios_program_service_freshness_checks_enabled',
            'Whether Nagios service freshness checking is enabled.',
        ],
        'check_host_freshness' => [
            'nagios_program_host_freshness_checks_enabled',
            'Whether Nagios host freshness checking is enabled.',
        ],
    ];

    foreach (
        $booleanMetrics as $statusKey => [$metricName, $help]
    ) {
        add_metric(
            $families,
            $metricName,
            $help,
            'gauge',
            [],
            $data[$statusKey] ?? null
        );
    }

    $windowMetrics = [
        'active_scheduled_host_check_stats' => [
            'nagios_program_active_scheduled_host_checks',
            'Nagios scheduled active host checks in the recent time window.',
        ],
        'active_ondemand_host_check_stats' => [
            'nagios_program_active_ondemand_host_checks',
            'Nagios on-demand active host checks in the recent time window.',
        ],
        'passive_host_check_stats' => [
            'nagios_program_passive_host_checks',
            'Nagios passive host checks in the recent time window.',
        ],
        'active_scheduled_service_check_stats' => [
            'nagios_program_active_scheduled_service_checks',
            'Nagios scheduled active service checks in the recent time window.',
        ],
        'active_ondemand_service_check_stats' => [
            'nagios_program_active_ondemand_service_checks',
            'Nagios on-demand active service checks in the recent time window.',
        ],
        'passive_service_check_stats' => [
            'nagios_program_passive_service_checks',
            'Nagios passive service checks in the recent time window.',
        ],
        'cached_host_check_stats' => [
            'nagios_program_cached_host_checks',
            'Nagios cached host checks in the recent time window.',
        ],
        'cached_service_check_stats' => [
            'nagios_program_cached_service_checks',
            'Nagios cached service checks in the recent time window.',
        ],
        'external_command_stats' => [
            'nagios_program_external_commands',
            'Nagios external commands processed in the recent time window.',
        ],
    ];

    foreach (
        $windowMetrics as $statusKey => [$metricName, $help]
    ) {
        if (!isset($data[$statusKey])) {
            continue;
        }

        emit_program_window_metric(
            $families,
            $data[$statusKey],
            $metricName,
            $help
        );
    }
}

try {
    $blocks = parse_status_dat($statusFile);

    $hostCount = 0;
    $serviceCount = 0;

    foreach ($blocks as [$type, $data]) {
        switch ($type) {
            case 'programstatus':
                emit_program_metrics(
                    $families,
                    $data
                );
                break;

            case 'hoststatus':
                $hostCount++;

                emit_host_metrics(
                    $families,
                    $data
                );
                break;

            case 'servicestatus':
                $serviceCount++;

                emit_service_metrics(
                    $families,
                    $data,
                    $servicePerfDataAllowList
                );
                break;
        }
    }

    add_metric(
        $families,
        'nagios_exporter_hosts',
        'Number of Nagios hoststatus blocks parsed.',
        'gauge',
        [],
        $hostCount
    );

    add_metric(
        $families,
        'nagios_exporter_services',
        'Number of Nagios servicestatus blocks parsed.',
        'gauge',
        [],
        $serviceCount
    );

    $statusFileMtime = filemtime($statusFile);

    if ($statusFileMtime !== false) {
        add_metric(
            $families,
            'nagios_exporter_status_file_age_seconds',
            'Age of the Nagios status.dat file in seconds.',
            'gauge',
            [],
            max(0, time() - $statusFileMtime)
        );
    }

    add_metric(
        $families,
        'nagios_exporter_up',
        'Nagios exporter health: 1=success, 0=failure.',
        'gauge',
        [],
        1
    );
} catch (Throwable $exception) {
    error_log(
        'Nagios metrics exporter error: '
        . $exception->getMessage()
    );

    add_metric(
        $families,
        'nagios_exporter_up',
        'Nagios exporter health: 1=success, 0=failure.',
        'gauge',
        [],
        0
    );
}

flush_metrics($families);