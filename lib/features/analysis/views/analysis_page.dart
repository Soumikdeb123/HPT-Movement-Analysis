import 'package:flutter/material.dart';

import '../models/analysis_result.dart';
import '../repositories/analysis_gateway.dart';
import '../repositories/mock_analysis_gateway.dart';
import '../view_models/analysis_view_model.dart';

class AnalysisPage extends StatefulWidget {
  const AnalysisPage({super.key, this.gateway});

  final AnalysisGateway? gateway;

  @override
  State<AnalysisPage> createState() => _AnalysisPageState();
}

class _AnalysisPageState extends State<AnalysisPage> {
  late final AnalysisViewModel viewModel;

  @override
  void initState() {
    super.initState();
    viewModel = AnalysisViewModel(
      widget.gateway ?? const MockAnalysisGateway(),
    );
  }

  @override
  void dispose() {
    viewModel.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: viewModel,
      builder: (context, child) {
        return Scaffold(
          appBar: AppBar(title: const Text('HPT Player Analysis')),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 900),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Analyse tennis movement',
                          style: Theme.of(context).textTheme.headlineMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Player-movement vertical slice: select a fixed-camera '
                          'video and review directional movement and workload. '
                          'Ball landing positions are outside the agreed scope.',
                          style: Theme.of(context).textTheme.bodyLarge,
                        ),
                        const SizedBox(height: 24),
                        _VideoCard(viewModel: viewModel),
                        const SizedBox(height: 16),
                        _OptionsCard(viewModel: viewModel),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          key: const Key('start-analysis-button'),
                          onPressed: viewModel.canStart
                              ? viewModel.startAnalysis
                              : null,
                          icon: const Icon(Icons.play_arrow),
                          label: const Text('Start analysis'),
                        ),
                        if (viewModel.isProcessing) ...[
                          const SizedBox(height: 24),
                          _ProgressPanel(progress: viewModel.progress),
                        ],
                        if (viewModel.status == AnalysisStatus.completed) ...[
                          const SizedBox(height: 24),
                          _ResultsPanel(result: viewModel.result!),
                          const SizedBox(height: 8),
                          TextButton(
                            onPressed: viewModel.reset,
                            child: const Text('Analyse another video'),
                          ),
                        ],
                        if (viewModel.status == AnalysisStatus.failed) ...[
                          const SizedBox(height: 24),
                          _ErrorPanel(
                            message:
                                viewModel.errorMessage ??
                                'An unexpected error occurred.',
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _VideoCard extends StatelessWidget {
  const _VideoCard({required this.viewModel});

  final AnalysisViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '1. Select video',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            const Text(
              'The current button uses a local prototype filename. A real '
              'video-picker service can replace it without changing this UI.',
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              key: const Key('select-video-button'),
              onPressed: viewModel.isProcessing
                  ? null
                  : viewModel.selectPrototypeVideo,
              icon: const Icon(Icons.video_library_outlined),
              label: const Text('Select prototype video'),
            ),
            if (viewModel.videoPath != null) ...[
              const SizedBox(height: 12),
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.movie_outlined),
                title: Text(viewModel.videoPath!),
                subtitle: const Text('Ready for prototype analysis'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _OptionsCard extends StatelessWidget {
  const _OptionsCard({required this.viewModel});

  final AnalysisViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '2. Configure analysis',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              key: const Key('player-selector'),
              initialValue: viewModel.selectedPlayer,
              decoration: const InputDecoration(labelText: 'Target player'),
              items: const [
                DropdownMenuItem(value: 'Player 1', child: Text('Player 1')),
                DropdownMenuItem(value: 'Player 2', child: Text('Player 2')),
              ],
              onChanged: viewModel.isProcessing ? null : viewModel.selectPlayer,
            ),
            const SizedBox(height: 8),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Experimental workload metrics'),
              subtitle: const Text(
                'Show speed, acceleration, deceleration and effort only after '
                'the movement trajectory has been validated.',
              ),
              value: viewModel.includeExperimentalSpeed,
              onChanged: viewModel.isProcessing
                  ? null
                  : viewModel.setExperimentalSpeed,
            ),
          ],
        ),
      ),
    );
  }
}

class _ProgressPanel extends StatelessWidget {
  const _ProgressPanel({required this.progress});

  final double progress;

  @override
  Widget build(BuildContext context) {
    final percentage = (progress * 100).round();

    return Semantics(
      label: 'Analysis progress',
      value: '$percentage percent',
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Processing video: $percentage%',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(value: progress),
              const SizedBox(height: 8),
              const Text('Keep this screen open while analysis is running.'),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultsPanel extends StatelessWidget {
  const _ResultsPanel({required this.result});

  final AnalysisResult result;

  @override
  Widget build(BuildContext context) {
    final workloadMetricsAvailable = result.speedSamples.isNotEmpty;

    return Card(
      key: const Key('analysis-results'),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Prototype results',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                if (result.isPrototype) const Chip(label: Text('Mock data')),
              ],
            ),
            const SizedBox(height: 4),
            const Text(
              'Player movement and workload only; ball landing positions are '
              'not included.',
            ),
            const SizedBox(height: 20),
            Text(
              'Directional movement',
              style: Theme.of(context).textTheme.titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            _MovementBreakdown(
              leftRightMetres: result.leftRightDistanceMetres,
              forwardBackMetres: result.forwardBackDistanceMetres,
            ),
            const SizedBox(height: 20),
            Text(
              'Movement and workload summary',
              style: Theme.of(context).textTheme.titleMedium
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            LayoutBuilder(
              builder: (context, constraints) {
                final cardWidth = constraints.maxWidth >= 620
                    ? (constraints.maxWidth - 12) / 2
                    : constraints.maxWidth;

                return Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    SizedBox(
                      width: cardWidth,
                      child: _MetricTile(
                        label: 'Total distance',
                        value: '${result.distanceMetres.toStringAsFixed(1)} m',
                        icon: Icons.route_outlined,
                      ),
                    ),
                    SizedBox(
                      width: cardWidth,
                      child: _MetricTile(
                        label: 'Direction changes',
                        value: '${result.directionChanges}',
                        icon: Icons.multiple_stop_outlined,
                      ),
                    ),
                    if (workloadMetricsAvailable) ...[
                      SizedBox(
                        width: cardWidth,
                        child: _MetricTile(
                          label: 'Average speed',
                          value:
                              '${result.averageSpeedKmh.toStringAsFixed(1)} km/h',
                          icon: Icons.speed_outlined,
                        ),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _MetricTile(
                          label: 'Peak speed',
                          value:
                              '${result.peakSpeedKmh.toStringAsFixed(1)} km/h',
                          icon: Icons.bolt_outlined,
                        ),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _MetricTile(
                          label: 'Peak acceleration',
                          value:
                              '${result.peakAccelerationMetresPerSecondSquared.toStringAsFixed(1)} m/s²',
                          icon: Icons.trending_up_outlined,
                        ),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _MetricTile(
                          label: 'Peak deceleration',
                          value:
                              '${result.peakDecelerationMetresPerSecondSquared.toStringAsFixed(1)} m/s²',
                          icon: Icons.trending_down_outlined,
                        ),
                      ),
                      SizedBox(
                        width: cardWidth,
                        child: _MetricTile(
                          label: 'Overall effort load',
                          value:
                              '${result.overallEffortLoad.toStringAsFixed(0)} / 100',
                          icon: Icons.monitor_heart_outlined,
                        ),
                      ),
                    ],
                  ],
                );
              },
            ),
            if (workloadMetricsAvailable) ...[
              const SizedBox(height: 16),
              _EffortLoadIndicator(value: result.overallEffortLoad),
              const SizedBox(height: 16),
              _SpeedProfile(samples: result.speedSamples),
            ],
            const SizedBox(height: 16),
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.ondemand_video_outlined),
              title: Text('Annotated video'),
              subtitle: Text('Awaiting backend video output'),
            ),
          ],
        ),
      ),
    );
  }
}

class _MovementBreakdown extends StatelessWidget {
  const _MovementBreakdown({
    required this.leftRightMetres,
    required this.forwardBackMetres,
  });

  final double leftRightMetres;
  final double forwardBackMetres;

  @override
  Widget build(BuildContext context) {
    final maxDistance = leftRightMetres >= forwardBackMetres
        ? leftRightMetres
        : forwardBackMetres;
    final leftRightRatio = maxDistance <= 0
        ? 0.0
        : leftRightMetres / maxDistance;
    final forwardBackRatio = maxDistance <= 0
        ? 0.0
        : forwardBackMetres / maxDistance;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _MovementBar(
              label: 'Left-right movement',
              value: '${leftRightMetres.toStringAsFixed(1)} m',
              ratio: leftRightRatio,
            ),
            const SizedBox(height: 16),
            _MovementBar(
              label: 'Forward-back movement',
              value: '${forwardBackMetres.toStringAsFixed(1)} m',
              ratio: forwardBackRatio,
            ),
            const SizedBox(height: 12),
            Text(
              'Bars compare the two accumulated directional components. '
              'They are not percentages of total court distance.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _MovementBar extends StatelessWidget {
  const _MovementBar({
    required this.label,
    required this.value,
    required this.ratio,
  });

  final String label;
  final String value;
  final double ratio;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      value: value,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(label)),
              Text(value, style: Theme.of(context).textTheme.titleSmall),
            ],
          ),
          const SizedBox(height: 6),
          LinearProgressIndicator(value: ratio.clamp(0, 1).toDouble()),
        ],
      ),
    );
  }
}

class _EffortLoadIndicator extends StatelessWidget {
  const _EffortLoadIndicator({required this.value});

  final double value;

  @override
  Widget build(BuildContext context) {
    final normalisedValue = (value / 100).clamp(0, 1).toDouble();

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Overall effort load — prototype index',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: normalisedValue),
            const SizedBox(height: 6),
            Text(
              '${value.toStringAsFixed(0)} / 100. The calculation must be '
              'validated with the client before coaching use.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _SpeedProfile extends StatelessWidget {
  const _SpeedProfile({required this.samples});

  final List<double> samples;

  @override
  Widget build(BuildContext context) {
    var peak = 0.0;
    for (final sample in samples) {
      if (sample > peak) {
        peak = sample;
      }
    }

    return Semantics(
      label: 'Speed profile',
      value: '${samples.length} samples; peak ${peak.toStringAsFixed(1)} km/h',
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Speed profile',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 12),
              SizedBox(
                height: 96,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    for (final sample in samples)
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 3),
                          child: FractionallySizedBox(
                            heightFactor: peak <= 0
                                ? 0
                                : (sample / peak).clamp(0.02, 1).toDouble(),
                            alignment: Alignment.bottomCenter,
                            child: DecoratedBox(
                              decoration: BoxDecoration(
                                color: Theme.of(context).colorScheme.primary,
                                borderRadius: const BorderRadius.vertical(
                                  top: Radius.circular(4),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Session sample sequence (km/h)',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label),
                  const SizedBox(height: 4),
                  Text(value, style: Theme.of(context).textTheme.titleMedium),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: ListTile(
        leading: Icon(
          Icons.error_outline,
          color: Theme.of(context).colorScheme.onErrorContainer,
        ),
        title: const Text('Analysis failed'),
        subtitle: Text(message),
      ),
    );
  }
}
