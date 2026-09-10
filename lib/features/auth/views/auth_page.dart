import 'package:flutter/material.dart';

import '../repositories/auth_repository.dart';

class AuthPage extends StatefulWidget {
  const AuthPage({super.key, required this.onSignedIn, this.repository});

  final VoidCallback onSignedIn;
  final AuthRepository? repository;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  late final _repository = widget.repository ?? AuthRepository();

  bool _registering = false;
  bool _busy = false;
  bool _hidePassword = true;
  String? _message;

  @override
  void dispose() {
    _username.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _switchMode() {
    if (_busy) return;

    _formKey.currentState?.reset();

    setState(() {
      _registering = !_registering;
      _password.clear();
      _hidePassword = true;
      _message = null;
    });
  }

  String? _validateEmail(String? value) {
    final email = value?.trim() ?? '';

    if (email.isEmpty) {
      return 'Please enter your email.';
    }

    if (!RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(email)) {
      return 'Please enter a valid email address.';
    }

    return null;
  }

  // 保留原 JavaScript 的密码强度规则。
  // 强度只是提示，不额外限制注册。
  String get _passwordStrength {
    final value = _password.text;

    if (value.isEmpty) {
      return 'Password strength: —';
    }

    final strong = RegExp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{10,}$');
    final medium = RegExp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$');

    if (strong.hasMatch(value)) {
      return 'Password strength: Strong';
    }

    if (medium.hasMatch(value)) {
      return 'Password strength: Medium';
    }

    return 'Password strength: Weak';
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (!(_formKey.currentState?.validate() ?? false)) return;

    FocusScope.of(context).unfocus();

    final registering = _registering;
    final email = _email.text.trim();
    final password = _password.text;
    final username = _username.text.trim();

    setState(() {
      _busy = true;
      _message = null;
    });

    try {
      if (registering) {
        await _repository.register(
          username: username,
          email: email,
          password: password,
        );

        if (!mounted) return;

        _formKey.currentState?.reset();

        setState(() {
          _registering = false;
          _username.clear();
          _email.text = email;
          _password.clear();
          _hidePassword = true;
          _message = 'Registration successful. Please sign in.';
        });
      } else {
        await _repository.login(email: email, password: password);

        if (!mounted) return;

        widget.onSignedIn();
      }
    } on AuthException catch (error) {
      if (!mounted) return;
      setState(() => _message = error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _message = 'An unexpected error occurred. Please try again.';
      });
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('HPT Player Analysis')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      _registering ? 'Create account' : 'Sign in',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 24),

                    if (_registering) ...[
                      TextFormField(
                        key: const ValueKey('username'),
                        controller: _username,
                        enabled: !_busy,
                        decoration: const InputDecoration(
                          labelText: 'Username',
                        ),
                        textInputAction: TextInputAction.next,
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Please enter your username.';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 16),
                    ],

                    TextFormField(
                      key: const ValueKey('email'),
                      controller: _email,
                      enabled: !_busy,
                      decoration: const InputDecoration(labelText: 'Email'),
                      keyboardType: TextInputType.emailAddress,
                      textCapitalization: TextCapitalization.none,
                      autocorrect: false,
                      textInputAction: TextInputAction.next,
                      validator: _validateEmail,
                    ),
                    const SizedBox(height: 16),

                    TextFormField(
                      key: const ValueKey('password'),
                      controller: _password,
                      enabled: !_busy,
                      obscureText: _hidePassword,
                      autocorrect: false,
                      enableSuggestions: false,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          tooltip: _hidePassword
                              ? 'Show password'
                              : 'Hide password',
                          onPressed: _busy
                              ? null
                              : () {
                                  setState(() {
                                    _hidePassword = !_hidePassword;
                                  });
                                },
                          icon: Icon(
                            _hidePassword
                                ? Icons.visibility
                                : Icons.visibility_off,
                          ),
                        ),
                      ),
                      textInputAction: TextInputAction.done,
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Please enter your password.';
                        }
                        return null;
                      },
                      onChanged: (_) {
                        if (_registering) {
                          setState(() {});
                        }
                      },
                      onFieldSubmitted: (_) => _submit(),
                    ),

                    if (_registering) ...[
                      const SizedBox(height: 8),
                      Text(_passwordStrength),
                    ],

                    if (_message != null) ...[
                      const SizedBox(height: 16),
                      Text(_message!, semanticsLabel: _message),
                    ],

                    const SizedBox(height: 24),

                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(_registering ? 'Sign Up' : 'Sign In'),
                    ),

                    const SizedBox(height: 12),

                    TextButton(
                      onPressed: _busy ? null : _switchMode,
                      child: Text(
                        _registering
                            ? 'Already have an account? Sign in'
                            : 'No account? Sign up',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
