import 'package:flutter/material.dart';

import '../../analysis/views/analysis_page.dart';
import '../../analysis/services/analysis_export_service.dart';
import '../../players/models/player_profile.dart';
import '../../players/repositories/player_repository.dart';
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
  String? _exporting;
  bool _selectionMode = false;
  bool _selectingAll = false;
  bool _batchDeleting = false;
  final Set<String> _selectedIds = {};
  final _exportService = AnalysisExportService();
  late final PlayerRepository _playerRepository;
  List<PlayerProfile> _players = const [];
  String? _selectedPlayerId;
  int _generation = 0;
  int _nextOffset = 0;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? AnalysisHistoryRepository();
    _playerRepository = PlayerRepository();
    _loadPlayers();
    _load();
  }

  @override
  void dispose() {
    _generation++;
    if (widget.repository == null) _repository.close();
    _playerRepository.close();
    super.dispose();
  }

  Future<void> _load({bool more = false}) async {
    if (more && _loading) return;
    final generation = ++_generation;
    final offset = more ? _nextOffset : 0;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final batch = await _repository.list(
        offset: offset,
        playerId: _selectedPlayerId,
      );
      if (!mounted || generation != _generation) {
        return;
      }
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
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _open(AnalysisHistoryEntry entry) async {
    final expired = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            _SavedAnalysisPage(id: entry.id, repository: _repository),
      ),
    );
    if (!mounted) return;
    if (expired == true) {
      Navigator.of(context).pop(true);
    } else {
      await _load();
    }
  }

  Future<void> _delete(AnalysisHistoryEntry entry) async {
    if (_deleting != null || _batchDeleting) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete analysis?'),
        content: Text(
          'Delete "${entry.videoName}" and its uploaded video, results and reports? '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _deleting = entry.id);
    try {
      await _repository.delete(entry.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Analysis deleted.')));
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

  void _leaveSelectionMode() {
    setState(() {
      _selectionMode = false;
      _selectedIds.clear();
    });
  }

  void _toggleSelection(AnalysisHistoryEntry entry) {
    if (entry.isRunning || _batchDeleting) return;
    setState(() {
      if (!_selectedIds.add(entry.id)) _selectedIds.remove(entry.id);
    });
  }

  Future<void> _selectAll() async {
    if (_loading || _selectingAll || _batchDeleting) return;
    final deletable = _items.where((item) => !item.isRunning).toList();
    final alreadyAll =
        deletable.isNotEmpty &&
        deletable.every((item) => _selectedIds.contains(item.id)) &&
        !_hasMore;
    if (alreadyAll) {
      setState(_selectedIds.clear);
      return;
    }
    setState(() => _selectingAll = true);
    try {
      var offset = _nextOffset;
      var hasMore = _hasMore;
      final ids = _items.map((item) => item.id).toSet();
      while (hasMore) {
        final batch = await _repository.list(
          offset: offset,
          playerId: _selectedPlayerId,
        );
        if (batch.items.isEmpty) break;
        _items.addAll(batch.items.where((item) => ids.add(item.id)));
        offset += batch.items.length;
        hasMore = batch.hasMore;
      }
      if (!mounted) return;
      setState(() {
        _hasMore = hasMore;
        _nextOffset = offset;
        _selectedIds
          ..clear()
          ..addAll(
            _items.where((item) => !item.isRunning).map((item) => item.id),
          );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _selectingAll = false);
    }
  }

  Future<void> _deleteSelected() async {
    if (_selectedIds.isEmpty || _batchDeleting) return;
    final count = _selectedIds.length;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Delete $count analyses?'),
        content: const Text(
          'Their uploaded videos, results and reports will also be deleted. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Delete all selected'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final ids = List<String>.of(_selectedIds);
    setState(() => _batchDeleting = true);
    try {
      for (final id in ids) {
        await _repository.delete(id);
      }
      if (!mounted) return;
      _selectionMode = false;
      _selectedIds.clear();
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$count analyses deleted.')));
      await _load();
    } catch (error) {
      if (!mounted) return;
      if (error is HistoryException && error.sessionExpired) {
        Navigator.of(context).pop(true);
      } else {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) setState(() => _batchDeleting = false);
    }
  }

  Future<void> _loadPlayers() async {
    try {
      final players = await _playerRepository.list();
      if (mounted) setState(() => _players = players);
    } on Object {
      // History remains usable even if the optional filter cannot load.
    }
  }

  Future<void> _export(AnalysisHistoryEntry entry) async {
    if (_exporting != null || entry.status != 'completed') return;
    setState(() => _exporting = entry.id);
    try {
      final saved = await _repository.get(entry.id);
      final result = saved.result;
      if (result == null) {
        throw StateError('This analysis has no completed report.');
      }
      final path = await _exportService.saveCoachReport(result);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            path == null ? 'Export cancelled.' : 'Coach PDF saved.',
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        setState(() => _error = 'Could not export the report. $error');
      }
    } finally {
      if (mounted) setState(() => _exporting = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          _selectionMode
              ? '${_selectedIds.length} selected'
              : 'Analysis History',
        ),
        actions: _selectionMode
            ? [
                IconButton(
                  key: const Key('select-all-history-button'),
                  tooltip: 'Select all',
                  onPressed: _selectingAll ? null : _selectAll,
                  icon: _selectingAll
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.select_all),
                ),
                IconButton(
                  key: const Key('delete-selected-history-button'),
                  tooltip: 'Delete selected',
                  onPressed: _selectedIds.isEmpty ? null : _deleteSelected,
                  icon: const Icon(Icons.delete_outline),
                ),
                IconButton(
                  tooltip: 'Cancel selection',
                  onPressed: _batchDeleting ? null : _leaveSelectionMode,
                  icon: const Icon(Icons.close),
                ),
              ]
            : [
                IconButton(
                  key: const Key('manage-history-button'),
                  tooltip: 'Select analyses',
                  onPressed: _items.any((item) => !item.isRunning)
                      ? () => setState(() => _selectionMode = true)
                      : null,
                  icon: const Icon(Icons.checklist),
                ),
                IconButton(
                  tooltip: 'Refresh',
                  onPressed: _loading ? null : () => _load(),
                  icon: const Icon(Icons.refresh),
                ),
              ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _load(),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(20),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 640),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text('Your analyses', style: theme.textTheme.headlineSmall),
                    const SizedBox(height: 8),
                    const Text(
                      'View your saved results, charts and annotated videos.',
                    ),
                    if (_players.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      DropdownButtonFormField<String>(
                        initialValue: _selectedPlayerId,
                        decoration: const InputDecoration(
                          labelText: 'Filter by player',
                          border: OutlineInputBorder(),
                        ),
                        items: [
                          const DropdownMenuItem(
                            value: '',
                            child: Text('All players'),
                          ),
                          for (final player in _players)
                            DropdownMenuItem(
                              value: player.id,
                              child: Text(player.name),
                            ),
                        ],
                        onChanged: (value) {
                          _selectedPlayerId = value == null || value.isEmpty
                              ? null
                              : value;
                          _load();
                        },
                      ),
                    ],
                    const SizedBox(height: 20),
                    if (_loading) ...[
                      const LinearProgressIndicator(),
                      const SizedBox(height: 16),
                    ],
                    if (_error != null) ...[
                      Text(
                        _error!,
                        style: TextStyle(color: theme.colorScheme.error),
                      ),
                      TextButton(
                        onPressed: _loading ? null : () => _load(),
                        child: const Text('Retry'),
                      ),
                      const SizedBox(height: 12),
                    ],
                    if (!_loading && _error == null && _items.isEmpty)
                      Card(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: const Padding(
                          padding: EdgeInsets.all(24),
                          child: Column(
                            children: [
                              Icon(Icons.history, size: 40),
                              SizedBox(height: 12),
                              Text('No analysis history yet.'),
                              SizedBox(height: 8),
                              Text(
                                'Upload a video and start an analysis. It will be saved here automatically.',
                                textAlign: TextAlign.center,
                              ),
                            ],
                          ),
                        ),
                      ),
                    for (final entry in _items) ...[
                      Card(
                        margin: EdgeInsets.zero,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                children: [
                                  if (_selectionMode)
                                    Checkbox(
                                      value: _selectedIds.contains(entry.id),
                                      onChanged: entry.isRunning
                                          ? null
                                          : (_) => _toggleSelection(entry),
                                    ),
                                  Expanded(
                                    child: Text(
                                      entry.videoName,
                                      style: theme.textTheme.titleMedium,
                                    ),
                                  ),
                                  if (!_selectionMode)
                                    IconButton(
                                      tooltip: 'Export coach PDF',
                                      onPressed:
                                          entry.status == 'completed' &&
                                              _exporting == null
                                          ? () => _export(entry)
                                          : null,
                                      icon: _exporting == entry.id
                                          ? const SizedBox.square(
                                              dimension: 18,
                                              child: CircularProgressIndicator(
                                                strokeWidth: 2,
                                              ),
                                            )
                                          : const Icon(
                                              Icons.picture_as_pdf_outlined,
                                            ),
                                    ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Text(
                                entry.playerName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(entry.dateLabel),
                              Text(
                                '${entry.targetPlayerLabel} · ${entry.statusLabel} · '
                                '${entry.qualityStatus == 'good'
                                    ? 'Good evidence'
                                    : entry.qualityStatus == 'limited'
                                    ? 'Limited evidence'
                                    : 'Evidence unavailable'}',
                              ),
                              if (entry.summary.isNotEmpty) ...[
                                const SizedBox(height: 12),
                                Text(entry.summary),
                              ],
                              if (entry.status == 'failed') ...[
                                const SizedBox(height: 8),
                                const Text(
                                  'Open this record to view the failure details.',
                                ),
                              ],
                              const SizedBox(height: 16),
                              OutlinedButton.icon(
                                key: ValueKey('view-analysis-${entry.id}'),
                                onPressed: !_selectionMode && _deleting == null
                                    ? () => _open(entry)
                                    : null,
                                icon: const Icon(Icons.analytics_outlined),
                                label: const Text('View analysis'),
                              ),
                              if (!entry.isRunning && !_selectionMode)
                                TextButton.icon(
                                  onPressed: _deleting == null
                                      ? () => _delete(entry)
                                      : null,
                                  style: TextButton.styleFrom(
                                    foregroundColor: theme.colorScheme.error,
                                  ),
                                  icon: const Icon(Icons.delete_outline),
                                  label: Text(
                                    _deleting == entry.id
                                        ? 'Deleting…'
                                        : 'Delete analysis',
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],
                    if (_hasMore)
                      OutlinedButton.icon(
                        onPressed: _loading ? null : () => _load(more: true),
                        icon: const Icon(Icons.expand_more),
                        label: const Text('Load more'),
                      ),
                  ],
                ),
              ),
            ),
          ],
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
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
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
    appBar: AppBar(
      title: const Text('Analysis details'),
      actions: [
        IconButton(
          tooltip: 'Refresh',
          onPressed: _loading ? null : _load,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 900),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_loading) const LinearProgressIndicator(),
                if (_error != null) ...[
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                  TextButton(
                    onPressed: _loading ? null : _load,
                    child: const Text('Retry'),
                  ),
                ],
                if (_saved case final saved?) ...[
                  Card(
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            saved.entry.videoName,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 8),
                          Text(saved.entry.dateLabel),
                          Text(
                            '${saved.entry.targetPlayerLabel} · ${saved.entry.statusLabel}',
                          ),
                          if (saved.entry.data['athleteMassKg']
                              case final num mass)
                            Text('Athlete mass used: $mass kg'),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (saved.result case final result?)
                    AnalysisResultsView(
                      result: result,
                      targetPlayerLabel: saved.entry.targetPlayerLabel,
                    )
                  else
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(
                          saved.entry.isRunning
                              ? 'This analysis is still running. Refresh to check its progress.'
                              : saved.entry.data['error']?.toString() ??
                                    'This analysis was cancelled.',
                        ),
                      ),
                    ),
                ],
              ],
            ),
          ),
        ),
      ],
    ),
  );
}
