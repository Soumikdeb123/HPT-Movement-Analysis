import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../repositories/auth_repository.dart';

class _AccountError implements Exception {
  const _AccountError(
    this.message, {
    this.expired = false,
  });

  final String message;
  final bool expired;

  @override
  String toString() => message;
}

class AccountPage extends StatefulWidget {
  const AccountPage({super.key});

  @override
  State<AccountPage> createState() => _AccountPageState();
}

class _AccountPageState extends State<AccountPage> {
  Map<String, dynamic>? _me;
  List<Map<String, dynamic>> _users = [];

  bool _busy = false;
  String? _error;
  String? _exitMessage;

  bool get _isAdmin => _me?['role'] == 'admin';

  @override
  void initState() {
    super.initState();
    _run(_load);
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final client = http.Client();

    try {
      final request = http.Request(
        method,
        Uri.parse('${AuthRepository.baseUrl}/api/auth$path'),
      );

      request.followRedirects = false;
      request.headers['Content-Type'] = 'application/json';

      final token = AuthRepository.token;

      if (token != null) {
        request.headers['Authorization'] = 'Bearer $token';
      }

      if (body != null) {
        request.body = jsonEncode(body);
      }

      final response = await (() async {
        final streamed = await client.send(request);
        return http.Response.fromStream(streamed);
      })().timeout(const Duration(seconds: 20));

      if (response.statusCode == 401) {
        throw const _AccountError(
          'Session ended. Please sign in again.',
          expired: true,
        );
      }

      Map<String, dynamic> data;

      try {
        final decoded = jsonDecode(response.body);

        if (decoded is! Map<String, dynamic>) {
          throw const FormatException();
        }

        data = decoded;
      } catch (_) {
        throw const _AccountError('Unexpected server response.');
      }

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw _AccountError(
          data['error']?.toString() ?? 'Request failed.',
        );
      }

      return data;
    } on TimeoutException {
      throw const _AccountError(
        'Request timed out. Please try again.',
      );
    } on http.ClientException {
      throw const _AccountError('Cannot connect to the server.');
    } finally {
      client.close();
    }
  }

  Future<void> _load() async {
    final me = await _request('GET', '/me');
    var users = <Map<String, dynamic>>[];

    if (me['role'] == 'admin') {
      final response = await _request('GET', '/users');

      users = (response['users'] as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    }

    if (!mounted) return;

    AuthRepository.userEmail = me['email'] as String?;

    setState(() {
      _me = me;
      _users = users;
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy || !mounted) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      await action();
    } catch (error) {
      if (!mounted) return;

      if (error is _AccountError && error.expired) {
        _exitMessage = error.message;
      } else {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);

        final message = _exitMessage;
        _exitMessage = null;

        if (message != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              _leave(message);
            }
          });
        }
      }
    }
  }

  void _message(String message) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  void _leave(String message) {
    if (!mounted) return;

    AuthRepository.clearSession();
    _message(message);

    Navigator.of(context).pop(true);
  }

  Future<List<String>?> _formDialog({
    required String title,
    required List<String> labels,
    List<String>? initialValues,
    Set<int> passwordFields = const {},
    String buttonText = 'Save',
    String? description,
    int? confirmPasswordIndex,
  }) {
    return showDialog<List<String>>(
      context: context,
      builder: (_) => _AccountFormDialog(
        title: title,
        labels: labels,
        initialValues: initialValues,
        passwordFields: passwordFields,
        buttonText: buttonText,
        description: description,
        confirmPasswordIndex: confirmPasswordIndex,
      ),
    );
  }

  Future<void> _editProfile() async {
    final values = await _formDialog(
      title: 'Edit Profile',
      labels: const [
        'Username',
        'Email',
        'Current password',
      ],
      initialValues: [
        _me?['username']?.toString() ?? '',
        _me?['email']?.toString() ?? '',
        '',
      ],
      passwordFields: const {2},
    );

    if (values == null || !mounted) return;

    await _run(() async {
      await _request('PATCH', '/me', {
        'username': values[0].trim(),
        'email': values[1].trim(),
        'currentPassword': values[2],
      });

      await _load();
      _message('Profile updated.');
    });
  }

  Future<void> _changePassword() async {
    final values = await _formDialog(
      title: 'Change Password',
      labels: const [
        'Current password',
        'New password',
        'Confirm new password',
      ],
      passwordFields: const {0, 1, 2},
      confirmPasswordIndex: 2,
      description:
          'Use at least 8 characters with uppercase, lowercase '
          'and a number. You will need to sign in again.',
    );

    if (values == null || !mounted) return;

    await _run(() async {
      await _request('PATCH', '/me/password', {
        'currentPassword': values[0],
        'newPassword': values[1],
      });

      _exitMessage = 'Password changed. Please sign in again.';
    });
  }

  Future<void> _deleteAccount() async {
    final values = await _formDialog(
      title: 'Delete Account?',
      labels: const ['Current password'],
      passwordFields: const {0},
      buttonText: 'Delete Account',
      description:
          'You will no longer be able to sign in with this account. '
          'Uploaded videos and analysis files are not erased '
          'by this action.',
    );

    if (values == null || !mounted) return;

    await _run(() async {
      await _request('DELETE', '/me', {
        'currentPassword': values[0],
      });

      _exitMessage = 'Account deleted.';
    });
  }

  Future<void> _logOut() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Log Out?'),
        content: const Text(
          'You will return to the sign-in page.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Log Out'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    _leave('You have been logged out.');
  }

  Future<void> _changeStatus(Map<String, dynamic> user) async {
    final restoring = user['status'] == 'disabled';
    final action = restoring ? 'Restore' : 'Disable';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('$action User?'),
        content: Text(user['email'].toString()),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(action),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    await _run(() async {
      await _request(
        'PATCH',
        '/users/${user['id']}/status',
        {
          'status': restoring ? 'active' : 'disabled',
        },
      );

      await _load();

      _message(
        restoring ? 'User restored.' : 'User disabled.',
      );
    });
  }

  String _displayValue(dynamic value) {
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? 'Not set' : text;
  }

  String _accountType(dynamic value) {
    switch (value?.toString()) {
      case 'admin':
        return 'Admin';
      case 'user':
        return 'User';
      default:
        return _displayValue(value);
    }
  }

  String _accountStatus(dynamic value) {
    switch (value?.toString()) {
      case 'active':
        return 'Active';
      case 'registered':
        return 'Registered';
      case 'disabled':
        return 'Disabled';
      case 'deleted':
        return 'Deleted';
      case 'email_updated':
        return 'Email updated';
      default:
        return _displayValue(value);
    }
  }

  Widget _profileField(String label, String value) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: theme.textTheme.labelLarge?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 6),
          SelectableText(
            value,
            style: theme.textTheme.titleMedium,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colours = theme.colorScheme;

    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Profile'),
          actions: [
            IconButton(
              tooltip: 'Refresh',
              onPressed: _busy ? null : () => _run(_load),
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 640),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_busy) ...[
                      const LinearProgressIndicator(),
                      const SizedBox(height: 16),
                    ],

                    if (_error != null) ...[
                      Text(
                        _error!,
                        style: TextStyle(color: colours.error),
                      ),
                      const SizedBox(height: 16),
                    ],

                    if (_me != null) ...[
                      Card(
                        margin: EdgeInsets.zero,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(24),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            crossAxisAlignment:
                                CrossAxisAlignment.stretch,
                            children: [
                              Row(
                                children: [
                                  CircleAvatar(
                                    radius: 30,
                                    backgroundColor:
                                        colours.primaryContainer,
                                    child: Icon(
                                      Icons.person,
                                      size: 36,
                                      color: colours.onPrimaryContainer,
                                    ),
                                  ),
                                  const SizedBox(width: 16),
                                  Expanded(
                                    child: Text(
                                      'Profile',
                                      style:
                                          theme.textTheme.headlineSmall,
                                    ),
                                  ),
                                ],
                              ),

                              const SizedBox(height: 32),

                              _profileField(
                                'Username',
                                _displayValue(_me!['username']),
                              ),
                              _profileField(
                                'Email',
                                _displayValue(_me!['email']),
                              ),
                              _profileField(
                                'Account type',
                                _accountType(_me!['role']),
                              ),
                              _profileField(
                                'Account status',
                                _accountStatus(_me!['status']),
                              ),

                              const Divider(),
                              const SizedBox(height: 16),

                              OutlinedButton.icon(
                                onPressed:
                                    _busy ? null : _editProfile,
                                icon: const Icon(Icons.edit_outlined),
                                label: const Text('Edit Profile'),
                              ),

                              const SizedBox(height: 8),

                              OutlinedButton.icon(
                                onPressed:
                                    _busy ? null : _changePassword,
                                icon: const Icon(Icons.lock_outline),
                                label: const Text('Change Password'),
                              ),

                              const SizedBox(height: 8),

                              OutlinedButton.icon(
                                onPressed: _busy ? null : _logOut,
                                icon: const Icon(Icons.logout),
                                label: const Text('Log Out'),
                              ),

                              if (!_isAdmin) ...[
                                const SizedBox(height: 8),
                                TextButton.icon(
                                  onPressed:
                                      _busy ? null : _deleteAccount,
                                  style: TextButton.styleFrom(
                                    foregroundColor: colours.error,
                                  ),
                                  icon: const Icon(
                                    Icons.delete_outline,
                                  ),
                                  label: const Text('Delete Account'),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),

                      if (_isAdmin) ...[
                        const SizedBox(height: 32),

                        Text(
                          'User management',
                          style: theme.textTheme.titleLarge,
                        ),

                        const SizedBox(height: 12),

                        for (final user in _users)
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    _displayValue(user['email']),
                                    style: theme.textTheme.titleMedium,
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Username: '
                                    '${_displayValue(user['username'])}',
                                  ),
                                  Text(
                                    'Account type: '
                                    '${_accountType(user['role'])}',
                                  ),
                                  Text(
                                    'Account status: '
                                    '${_accountStatus(user['status'])}',
                                  ),

                                  if (user['role'] == 'user' &&
                                      user['status'] != 'deleted') ...[
                                    const SizedBox(height: 12),
                                    Align(
                                      alignment: Alignment.centerRight,
                                      child: OutlinedButton(
                                        onPressed: _busy
                                            ? null
                                            : () => _changeStatus(user),
                                        child: Text(
                                          user['status'] == 'disabled'
                                              ? 'Restore User'
                                              : 'Disable User',
                                        ),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                      ],
                    ],

                    if (_me == null && !_busy)
                      OutlinedButton.icon(
                        onPressed: _logOut,
                        icon: const Icon(Icons.logout),
                        label: const Text('Log Out'),
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

class _AccountFormDialog extends StatefulWidget {
  const _AccountFormDialog({
    required this.title,
    required this.labels,
    required this.passwordFields,
    required this.buttonText,
    this.initialValues,
    this.description,
    this.confirmPasswordIndex,
  });

  final String title;
  final List<String> labels;
  final List<String>? initialValues;
  final Set<int> passwordFields;
  final String buttonText;
  final String? description;
  final int? confirmPasswordIndex;

  @override
  State<_AccountFormDialog> createState() => _AccountFormDialogState();
}

class _AccountFormDialogState extends State<_AccountFormDialog> {
  final _formKey = GlobalKey<FormState>();
  late final List<TextEditingController> _controllers;

  @override
  void initState() {
    super.initState();

    _controllers = List.generate(
      widget.labels.length,
      (index) => TextEditingController(
        text: widget.initialValues?[index] ?? '',
      ),
    );
  }

  @override
  void dispose() {
    for (final controller in _controllers) {
      controller.dispose();
    }

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SingleChildScrollView(
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.description != null) ...[
                Text(widget.description!),
                const SizedBox(height: 16),
              ],

              for (var i = 0; i < widget.labels.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextFormField(
                    controller: _controllers[i],
                    obscureText: widget.passwordFields.contains(i),
                    autocorrect: !widget.passwordFields.contains(i),
                    enableSuggestions:
                        !widget.passwordFields.contains(i),
                    decoration: InputDecoration(
                      labelText: widget.labels[i],
                      border: const OutlineInputBorder(),
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Required';
                      }

                      if (i == widget.confirmPasswordIndex &&
                          i > 0 &&
                          value != _controllers[i - 1].text) {
                        return 'Passwords do not match';
                      }

                      return null;
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            if (!_formKey.currentState!.validate()) return;

            Navigator.pop(
              context,
              _controllers.map((item) => item.text).toList(),
            );
          },
          child: Text(widget.buttonText),
        ),
      ],
    );
  }
}