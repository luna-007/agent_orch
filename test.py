import subprocess

result = subprocess.run(["ls"], capture_output=True, text=True)
print(result.stdout)
for i in result.stdout:
    print(i)