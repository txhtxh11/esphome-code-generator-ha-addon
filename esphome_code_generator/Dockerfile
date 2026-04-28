FROM esphome/esphome:latest

# Copy code generator backend module
COPY code_generator.py /esphome/esphome/dashboard/code_generator.py

# Copy your custom index.html to a known location
COPY index.html /data/index.html

# Patch web_server.py to add /generate route
RUN /usr/local/bin/python3 << 'PYEOF'
web_server_path = "/esphome/esphome/dashboard/web_server.py"

with open(web_server_path, "r") as f:
    content = f.read()

# 1. Add import
import_line = "from .code_generator import CodeGeneratorHandler\n"
insert_pos = content.find("from .core import DASHBOARD")
if insert_pos >= 0:
    end_pos = content.index("\n", insert_pos) + 1
    content = content[:end_pos] + import_line + content[end_pos:]
    print("[OK] Import added")
else:
    print("[FAIL] Import insertion point not found!")
    exit(1)

# 2. Add route
old_route = '(f"{rel}version", EsphomeVersionHandler),'
assert old_route in content, "Route not found!"
new_route = '(f"{rel}generate", CodeGeneratorHandler),\n            (f"{rel}generate/api", CodeGeneratorHandler),\n            ' + old_route
content = content.replace(old_route, new_route)
print("[OK] Route added")

with open(web_server_path, "w") as f:
    f.write(content)

print("[OK] web_server.py patched successfully")
PYEOF

# Patch the frontend JS: Add "Code Generator (Visual)" option to New Device dialog
COPY <<'PYEOF' /tmp/patch_js.py
import os, glob

js_dir = "/usr/local/lib/python3.12/site-packages/esphome_dashboard/static/js/esphome"
for f in glob.glob(os.path.join(js_dir, "c.*.js")):
    with open(f) as fh:
        content = fh.read()
    if "<span>Empty Configuration</span>" in content:
        break
else:
    print("[FAIL] Empty Configuration not found in any JS file!")
    exit(1)

print("[OK] Found Wizard dialog in %s" % os.path.basename(f))

target = "<span>Empty Configuration</span>"
idx = content.find(target)
end_item = content.find("</mwc-list-item>", idx)
after = content.find("</mwc-list>", end_item)

new_item = """\
          <mwc-list-item
            twoline
            hasMeta
            @click=${()=>{window.open("./generate", "_self")}}
          >
            <span>Code Generator (Visual)</span>
            <span slot="secondary"
              >Visually configure sensors, switches, lights and generate YAML.</span
            >
            ${I}
          </mwc-list-item>
"""

content = content[:end_item + len("</mwc-list-item>")] + new_item + content[after:]

with open(f, "w") as fh:
    fh.write(content)

print("[OK] JS patched: Code Generator option added to New Device dialog")
PYEOF

RUN /usr/local/bin/python3 /tmp/patch_js.py

# Verify the patch works
RUN /usr/local/bin/python3 -c 'from esphome.dashboard.code_generator import CodeGeneratorHandler; from esphome.dashboard.web_server import make_app; print("[code-gen] All imports OK - build successful")'

# Expose the ESPHome dashboard port
EXPOSE 6052

# Start ESPHome dashboard
CMD ["esphome", "dashboard", "/config"]