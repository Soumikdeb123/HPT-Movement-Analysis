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
                          'Prototype vertical slice: select a fixed-camera '
                          'video, configure the analysis and review the result.',
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
              title: const Text('Experimental speed curve'),
              subtitle: const Text(
                'Display only after trajectory and distance validation.',
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
            const SizedBox(height: 16),
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
                        label: 'Trajectory',
                        value: 'Mock path available',
                        icon: Icons.timeline_outlined,
                      ),
                    ),
                    if (result.speedSamples.isNotEmpty) ...[
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
                    ],
                  ],
                );
              },
            ),
            const SizedBox(height: 16),
            const ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.grid_view_outlined),
              title: Text('Heatmap'),
              subtitle: Text('Awaiting backend image output'),
            ),
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
