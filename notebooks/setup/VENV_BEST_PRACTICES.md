# Virtual Environment Best Practices for Jupyter Notebooks

## Quick Answer

**Best Practice:** Create the virtual environment **BEFORE** starting Jupyter.

## Why?

When you create a venv inside a Jupyter notebook:
- The notebook kernel is still running in the original Python environment
- You can't easily switch to the new venv without restarting
- It requires extra steps (install ipykernel, register kernel, restart)
- More error-prone and confusing for users

## Recommended Approach

### Option 1: Create venv first (RECOMMENDED)

```bash
# 1. Create virtual environment
python3 -m venv env

# 2. Activate it
source env/bin/activate  # Linux/Mac
# or
env\Scripts\activate  # Windows

# 3. Install Jupyter and ipykernel
pip install jupyter ipykernel

# 4. Register the venv as a Jupyter kernel
python -m ipykernel install --user --name=warehouse-assistant

# 5. Start Jupyter from the venv
jupyter notebook notebooks/setup/complete_setup_guide.ipynb

# 6. Select the kernel: Kernel → Change Kernel → warehouse-assistant
```

**Benefits:**
- ✅ Clean and straightforward
- ✅ Kernel uses the correct environment from the start
- ✅ No need to restart or switch kernels
- ✅ All dependencies available immediately

### Option 2: Create venv in notebook (Alternative)

The notebook supports creating the venv inside, but it requires:

1. Create venv (notebook cell)
2. Install ipykernel in the new venv
3. Register the kernel
4. **Restart the kernel** (important!)
5. Switch to the new kernel
6. Re-run cells to verify

**When to use:**
- You're already in Jupyter and want to set up the environment
- You're following the notebook step-by-step
- You don't mind the extra steps

## How to Check Your Current Kernel

Run this in a notebook cell:

```python
import sys
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Check if in venv
in_venv = hasattr(sys, 'real_prefix') or (
    hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
)
print(f"In virtual environment: {in_venv}")
if in_venv:
    print(f"Venv path: {sys.prefix}")
```

## Switching Kernels

If you need to switch kernels after creating the venv:

1. **In Jupyter Notebook:**
   - Go to: `Kernel → Change Kernel → warehouse-assistant`

2. **In JupyterLab:**
   - Click the kernel name in the top right
   - Select: `warehouse-assistant`

3. **Verify:**
   - Re-run the kernel check cell
   - Should show the venv's Python path

## Troubleshooting

### "Kernel not found"
```bash
# Make sure ipykernel is installed in the venv
source env/bin/activate
pip install ipykernel
python -m ipykernel install --user --name=warehouse-assistant
```

### "Wrong Python version"
- Check that you're using the correct kernel
- Verify the kernel points to the venv's Python

### "Module not found" errors
- Make sure you're using the correct kernel
- Verify packages are installed in the venv (not system Python)
- Restart the kernel after installing packages

## Summary

| Approach | Complexity | Recommended For |
|----------|-----------|-----------------|
| Create venv first | ⭐ Simple | New users, production |
| Create in notebook | ⭐⭐ Medium | Following notebook guide |

**For the setup notebook:** Either approach works, but creating the venv first is cleaner and less error-prone.

