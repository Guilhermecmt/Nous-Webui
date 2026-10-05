# Contributing to Nous WebUI

We welcome contributions! By participating in this project you agree to follow these simple steps:

## How to Contribute

1. **Fork the repository** and clone your fork locally.
2. **Create a new branch** for your feature or bug fix:
   ```bash
   git checkout -b my-feature
   ```
3. **Make your changes** – follow the coding style used in the existing code (Windows batch and PowerShell scripts, JavaScript/HTML, and Python).  Keep the repository Windows‑friendly.
4. **Add tests** if applicable.  The project currently does not have an automated test suite, but adding a small sanity‑check script is appreciated.
5. **Commit with clear messages**:
   ```bash
   git commit -m "feat: brief description"
   ```
6. **Push to your fork** and open a Pull Request against `main`.

## Pull Request Checklist
- [ ] Description of the change and why it is needed.
- [ ] Ensure the code builds/runs on Windows 10/11.
- [ ] Update the README if the public interface changes.
- [ ] Verify the license header (MIT) remains unchanged.

## Coding Style
- Use **four spaces** for indentation in PowerShell and batch files.
- Keep line lengths under 120 characters.
- Use **PascalCase** for PowerShell function names and **snake_case** for batch variables.
- For HTML/Markdown files, follow the existing formatting style.

## Reporting Issues
If you encounter a bug, please open an issue using the provided template and include:
- OS version (Windows 10/11)
- Steps to reproduce
- Expected vs. actual behavior
- Any relevant logs from `tools\check-system.ps1`.

Thank you for helping make Nous WebUI better!
