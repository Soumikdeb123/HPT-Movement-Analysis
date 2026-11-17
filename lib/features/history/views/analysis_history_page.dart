import 'package:flutter/material.dart';

import '../../analysis/views/analysis_page.dart';
import '../repositories/analysis_history_repository.dart';

class AnalysisHistoryPage extends StatefulWidget {
  const AnalysisHistoryPage({super.key, this.repository});
  final AnalysisHistoryRepository? repository;
  @override
  State<AnalysisHistoryPage> createState() => _AnalysisHistoryPageState();
}

class _AnalysisHistoryPageState extends State<AnalysisHistoryPage> {
  late final AnalysisHistoryRepository _repository;
  final List<AnalysisHistoryEntry> _items = [];
  bool _loading = true;
  bool _hasMore = false;
  String? _error;
  String? _deleting;
  int _generation = 0;
  int _nextOffset = 0;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AnalysisHistoryRepository();
    _load();
  }

  @override
  void dispose() {
    _generation++;
    if (widget.repository == null) _repository.close();
    super.dispose();
  }

  Future<void> _load({bool more = false}) async {
    if (more && _loading) return;
    final generation = ++_generation;
    final offset = more ? _nextOffset : 0;
    setState(() { _loading = true; _error = null; });
    try {
      final batch = await _repository.list(offset: offset);
      if (!mounted || generation != _generation) return;
      setState(() {
        if (!more) _items.clear();
        // Offset pages can overlap if a new job was created during navigation.
        final ids = _items.map((item) => item.id).toSet();
        _items.addAll(batch.items.where((item) => ids.add(item.id)));
        _hasMore = batch.hasMore;
        _nextOffset = offset + batch.items.length;
      });
    } catch (error) {
      if (!mounted || generation != _generation) return;
      if (error is HistoryException && error.sessionExpired) {
        Navigator.of(context).pop(true);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted && generation == _generation) setState(() => _loading = false);
    }
  }

  Future<void> _open(AnalysisHistoryEntry entry) async {
    final expired = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => _SavedAnalysisPage(id: entry.id, repository: _repository),
    ));
    if (!mounted) return;
    if (expired == true) {
      Navigator.of(context).pop(true);
    } else {
      await _load();
    }
  }

  Future<void> _delete(AnalysisHistoryEntry entry) async {
    if (_deleting != null) return;
    final confirmed = await showDialog<bool>(context: context, builder: (dialogContext) =>
      AlertDialog(
        title: const Text('Delete analysis?'),
        content: Text('Delete "${entry.videoName}" and its uploaded video, results and reports? '
            'This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Delete')),
        ],
      ));
    if (confirmed != true || !mounted) return;
    setState(() => _deleting = entry.id);
    try {
      await _repository.delete(entry.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Analysis deleted.')));
      await _load();
    } catch (error) {
      if (!mounted) return;
      if (error is HistoryException && error.sessionExpired) {
        Navigator.of(context).pop(true);
      } else {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) setState(() => _deleting = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Analysis History'), actions: [
        IconButton(tooltip: 'Refresh', onPressed: _loading ? null : () => _load(),
            icon: const Icon(Icons.refresh)),
      ]),
      body: RefreshIndicator(
        onRefresh: () => _load(),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(20),
          children: [Center(child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('Your analyses', style: theme.textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text('View your saved results, charts and annotated videos.'),
              const SizedBox(height: 20),
              if (_loading) ...[const LinearProgressIndicator(), const SizedBox(height: 16)],
              if (_error != null) ...[
                Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                TextButton(onPressed: _loading ? null : () => _load(), child: const Text('Retry')),
                const SizedBox(height: 12),
              ],
              if (!_loading && _error == null && _items.isEmpty)
                Card(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                  child: const Padding(padding: EdgeInsets.all(24), child: Column(children: [
                    Icon(Icons.history, size: 40), SizedBox(height: 12),
                    Text('No analysis history yet.'), SizedBox(height: 8),
                    Text('Upload a video and start an analysis. It will be saved here automatically.',
                        textAlign: TextAlign.center),
                  ]))),
              for (final entry in _items) ...[
                Card(margin: EdgeInsets.zero,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
                  child: Padding(padding: const EdgeInsets.all(24), child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                      Text(entry.videoName, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 8),
                      Text(entry.dateLabel),
                      Text('${entry.targetPlayerLabel} · ${entry.statusLabel}'),
                      if (entry.summary.isNotEmpty) ...[
                        const SizedBox(height: 12), Text(entry.summary),
                      ],
                      if (entry.status == 'failed') ...[
                        const SizedBox(height: 8),
                        const Text('Open this record to view the failure details.'),
                      ],
                      const SizedBox(height: 16),
                      OutlinedButton.icon(
                        key: ValueKey('view-analysis-${entry.id}'),
                        onPressed: _deleting == null ? () => _open(entry) : null,
                        icon: const Icon(Icons.analytics_outlined),
                        label: const Text('View analysis'),
                      ),
                      if (!entry.isRunning) TextButton.icon(
                        onPressed: _deleting == null ? () => _delete(entry) : null,
                        style: TextButton.styleFrom(foregroundColor: theme.colorScheme.error),
                        icon: const Icon(Icons.delete_outline),
                        label: Text(_deleting == entry.id ? 'Deleting…' : 'Delete analysis'),
                      ),
                    ],
                  )),
                ),
                const SizedBox(height: 16),
              ],
              if (_hasMore) OutlinedButton.icon(
                onPressed: _loading ? null : () => _load(more: true),
                icon: const Icon(Icons.expand_more), label: const Text('Load more'),
              ),
            ]),
          ))],
        ),
      ),
    );
  }
}

class _SavedAnalysisPage extends StatefulWidget {
  const _SavedAnalysisPage({required this.id, required this.repository});
  final String id;
  final AnalysisHistoryRepository repository;
  @override
  State<_SavedAnalysisPage> createState() => _SavedAnalysisPageState();
}

class _SavedAnalysisPageState extends State<_SavedAnalysisPage> {
  SavedAnalysis? _saved;
  bool _loading = true;
  String? _error;

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final saved = await widget.repository.get(widget.id);
      if (mounted) setState(() => _saved = saved);
    } catch (error) {
      if (!mounted) return;
      if (error is HistoryException && error.sessionExpired) {
        Navigator.of(context).pop(true);
        return;
      }
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Analysis details'), actions: [
      IconButton(tooltip: 'Refresh', onPressed: _loading ? null : _load,
          icon: const Icon(Icons.refresh)),
    ]),
    body: ListView(padding: const EdgeInsets.all(20), children: [
      Center(child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 900),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) ...[
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            TextButton(onPressed: _loading ? null : _load, child: const Text('Retry')),
          ],
          if (_saved case final saved?) ...[
            Card(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              child: Padding(padding: const EdgeInsets.all(24), child: Column(
                crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(saved.entry.videoName, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8), Text(saved.entry.dateLabel),
                  Text('${saved.entry.targetPlayerLabel} · ${saved.entry.statusLabel}'),
                  if (saved.entry.data['athleteMassKg'] case final num mass)
                    Text('Athlete mass used: $mass kg'),
                ]))),
            const SizedBox(height: 16),
            if (saved.result case final result?)
              AnalysisResultsView(result: result,
                  targetPlayerLabel: saved.entry.targetPlayerLabel)
            else Card(child: Padding(padding: const EdgeInsets.all(24), child: Text(
              saved.entry.isRunning
                  ? 'This analysis is still running. Refresh to check its progress.'
                  : saved.entry.data['error']?.toString() ?? 'This analysis was cancelled.',
            ))),
          ],
        ]),
      )),
    ]),
  );
}
