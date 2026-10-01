#!/usr/bin/env python3
"""PROPOSED additions for ~/.claude/skills/fix-claude-plugin/patch.py
(patch 7: files sent with SendUserFile render inline in the IDE webview).

The auto-mode classifier refused the edits to patch.py itself, so this file
holds the exact pieces for review. It is also runnable STANDALONE:

    python3 patch7_send_user_file.py            # apply 7a/7b/7c to every bundle
    python3 patch7_send_user_file.py --check    # dry run, report only

Standalone mode re-uses find_bundles() from the skill's patch.py.

To fold into patch.py permanently:
  1. append the three PATCH_7 entries to PATCHES,
  2. add `_send_user_file_ctx` + `SEND_USER_FILE_TOOL_JS` at module level,
  3. replace the inner loop of patch_file() with `_apply_patch()` below
     (adds `context` support: replace(match, ctx)).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/fix-claude-plugin"))
import patch as skill_patch  # noqa: E402  (find_bundles, EXT_GLOBS)


def _send_user_file_ctx(text):
    """Resolve the minified names patch 7c needs from the tool-renderer base
    class:  class z2{hidden=!1;header($,J){return D(L1,{children:D("span",
    {className:K0.toolNameText,children:this.name})})}body($,J,Z,Y){...
    return E(L1,{children:[   ->  BASE=z2 JSX=D FRAG=L1 CSS=K0 JSXS=E.
    2.1.286 added a 5th body() argument (replay / denial metadata), hence the
    optional trailing parameter."""
    m = re.search(
        r'class ([\w$]+)\{hidden=!1;header\(([\w$]+),([\w$]+)\)\{return ([\w$]+)\(([\w$]+),'
        r'\{children:\4\("span",\{className:([\w$]+)\.toolNameText,children:this\.name\}\)\}\)\}'
        r'body\(([\w$]+),([\w$]+),([\w$]+),([\w$]+)(?:,[\w$]+)?\)\{let [\w$]+=this\.renderInput\(\7,\8\),'
        r'[\w$]+=this\.renderOutput\(\7,\9,\8\),[\w$]+=this\.toolDescription\(\8\);'
        r'return ([\w$]+)\(\5,\{children:\[',
        text,
    )
    if not m:
        return None
    return {
        "BASE": m.group(1), "JSX": m.group(4), "FRAG": m.group(5),
        "CSS": m.group(6), "JSXS": m.group(11),
    }


# Renderer source for patch 7c. {BASE} etc. come from _send_user_file_ctx;
# literal braces are doubled. One line, so the `already` regex is a plain
# substring and the bundle keeps one statement per line.
SEND_USER_FILE_TOOL_JS = (
    'class CcSendUserFileTool extends {BASE}{{name="SendUserFile";'
    'constructor(o){{super();this.opener=o}}'
    # origin of the loaded webview/index.js = the vscode-resource authority of
    # the extension host's filesystem (local: https://file+.vscode-resource...,
    # Remote-SSH: https://vscode-remote+ssh-002dremote-002b<host>....)
    'static origin(){{try{{var s=Array.prototype.map.call(document.scripts,function(x){{return x.src}})'
    '.filter(function(x){{return /\\/webview\\/index\\.js/.test(x)}})[0];'
    'return s?new URL(s).origin:null}}catch(e){{return null}}}}'
    'static url(p){{var o=CcSendUserFileTool.origin();if(!o||typeof p!=="string"||p[0]!=="/")return null;'
    'return o+p.split("/").map(encodeURIComponent).join("/")}}'
    'static kind(p){{var m=/\\.([a-z0-9]+)$/i.exec(p||""),e=m?m[1].toLowerCase():"";'
    'if(/^(png|jpe?g|gif|webp|svg|bmp|avif|ico)$/.test(e))return"image";'
    'if(/^(mp4|webm|mov|m4v|ogv|mkv)$/.test(e))return"video";'
    'if(/^(mp3|wav|ogg|oga|m4a|flac|aac)$/.test(e))return"audio";return"file"}}'
    'static text(r){{if(!r)return"";if(typeof r.content==="string")return r.content;'
    'if(Array.isArray(r.content))return r.content.map(function(c){{return c&&c.type==="text"?c.text:""}}).join("\\n");return""}}'
    # absolute paths from the result ("<path> → file_uuid: ..."), else the input
    'static paths(i,r){{var a=Array.isArray(i&&i.files)?i.files.filter(function(x){{return typeof x==="string"}}):[],b=[];'
    'CcSendUserFileTool.text(r).replace(/^\\s*(\\/.+?)\\s+\\u2192\\s+file_uuid:/gm,function(_,p){{b.push(p);return _}});'
    'return b.length&&b.length===a.length?b:a}}'
    'header(c,i){{var f=Array.isArray(i&&i.files)?i.files:[],n=f.map(function(p){{return String(p).split("/").pop()}}).join(", ");'
    'return {JSXS}({FRAG},{{children:[{JSX}("span",{{className:{CSS}.toolNameText,children:f.length>1?"Sent files":"Sent file"}})," ",'
    '{JSX}("span",{{className:{CSS}.toolNameTextSecondary,children:n}})]}})}}'
    'body(c,i,r,g,x){{if(!r)return null;if(r.is_error)return super.body(c,i,r,g,x);'
    'var self=this,ps=CcSendUserFileTool.paths(i,r),attach=!!i&&i.display==="attach",'
    'items=ps.map(function(p,k){{var u=CcSendUserFileTool.url(p),kind=attach?"file":CcSendUserFileTool.kind(p),name=p.split("/").pop(),'
    'open=function(ev){{if(ev&&ev.preventDefault)ev.preventDefault();self.opener.open(p)}},el=null;'
    'if(u&&kind==="image")el={JSX}("img",{{src:u,alt:name,title:"Open "+p,onClick:open,'
    'style:{{maxWidth:"100%",maxHeight:"480px",display:"block",borderRadius:"6px",cursor:"pointer"}}}});'
    'else if(u&&kind==="video")el={JSX}("video",{{src:u,controls:!0,preload:"metadata",title:p,'
    'style:{{maxWidth:"100%",maxHeight:"480px",display:"block",borderRadius:"6px"}}}});'
    'else if(u&&kind==="audio")el={JSX}("audio",{{src:u,controls:!0,preload:"metadata",title:p,style:{{display:"block",width:"100%"}}}});'
    'return {JSXS}("div",{{style:{{display:"flex",flexDirection:"column",gap:"4px"}},children:[el,'
    '{JSX}("a",{{href:"#",onClick:open,title:p,style:{{fontSize:"0.85em",opacity:.75,wordBreak:"break-all"}},children:name}})]}},k)}});'
    'return {JSXS}("div",{{style:{{display:"flex",flexDirection:"column",gap:"10px",padding:"6px 0"}},'
    'children:[i&&i.caption?{JSX}("div",{{className:{CSS}.toolBodyPlainText,children:i.caption}}):null].concat(items)}})}}}}'
)


PATCH_7 = [
    {
        "name": "7a SendUserFile inline media: CSP media-src",
        "target": "extension.js",
        # getHtmlForWebview(): N=`img-src ${$.cspSource} data:` -- no media-src
        # at all and default-src 'none', so <video>/<audio> from the webview
        # resource host are blocked. Extend the same directive string.
        "find": re.compile(r'(img-src \$\{([\w$]+)\.cspSource\} data:)(?=`)'),
        "replace": lambda m: f'{m.group(1)}; media-src ${{{m.group(2)}.cspSource}}',
        "already": re.compile(r'media-src \$\{[\w$]+\.cspSource\}'),
    },
    {
        "name": '7b SendUserFile inline media: localResourceRoots += Uri.file("/")',
        "target": "extension.js",
        # All 4 webview/panel creation sites use
        #   localResourceRoots:[X.Uri.joinPath(this.extensionUri,"webview"),
        #                       X.Uri.joinPath(this.extensionUri,"resources")]
        # Requests outside those roots are refused, so a file under $HOME or
        # /tmp could never load. Add the filesystem root (the extension host
        # already reads any of these files for the webview anyway).
        "find": re.compile(
            r'(localResourceRoots:\[([\w$]+)\.Uri\.joinPath\(this\.extensionUri,"webview"\),'
            r'\2\.Uri\.joinPath\(this\.extensionUri,"resources"\))\]'
        ),
        "replace": lambda m: f'{m.group(1)},{m.group(2)}.Uri.file("/")]',
        "already": re.compile(
            r'localResourceRoots:\[[\w$]+\.Uri\.joinPath\(this\.extensionUri,"webview"\),'
            r'[\w$]+\.Uri\.joinPath\(this\.extensionUri,"resources"\),[\w$]+\.Uri\.file\("/"\)\]'
        ),
    },
    {
        "name": "7c SendUserFile inline media: webview tool renderer",
        "target": "webview/index.js",
        # Renderers extend the base class (name/header/body/renderInput/
        # renderOutput) and are looked up by tool name in
        #   function BG($,J){let Z=[new u51,...,new uV1(J.fileOpener),...],
        #     Y=$==="Task"?"Agent":$,X=Z.find((Q)=>Q.name===Y);if(X)return X;
        #     ... return new eV1($)}        // generic IN/OUT fallback
        # Define CcSendUserFileTool right before the registry function and
        # prepend it to the list.
        "context": _send_user_file_ctx,
        "find": re.compile(
            r'(?<![\w$])(function [\w$]+\(([\w$]+),([\w$]+)\)\{let [\w$]+=\[)'
            r'(?=new [\w$]+,new [\w$]+,[^;]{0,2000}?new [\w$]+\(\3\.fileOpener\)[^;]{0,2000}?'
            r'\.find\(\(([\w$]+)\)=>\4\.name===)'
        ),
        "replace": lambda m, ctx: (
            SEND_USER_FILE_TOOL_JS.format(**ctx)
            + f'{m.group(1)}new CcSendUserFileTool({m.group(3)}.fileOpener),'
        ),
        "already": re.compile(r'class CcSendUserFileTool extends [\w$]+\{name="SendUserFile"'),
    },
    {
        "name": "8 clicked file links: media/binary files open with vscode.open",
        "target": "extension.js",
        # A markdown link such as [file-653.mp4](/abs/path/file-653.mp4) in an
        # assistant message goes webview Bj0() -> RC() (path + optional
        # :L12-L20) -> fileOpener.open() -> extension openFile(), which ends in
        #   _$.window.showTextDocument(X).then((z)=>{ ...reveal range... })
        # showTextDocument() only knows text documents: for an mp4 / png /
        # pdf it REJECTS ("binary or unsupported encoding") and nothing has a
        # catch, so the click does nothing. Media files (images, video,
        # audio, pdf) get a fast path through the `vscode.open` command,
        # which routes to the built-in Media Preview / image / pdf editors,
        # and every other rejection falls back to `vscode.open` as well
        # (VS Code then offers "Open Anyway" for unknown binaries).
        # (Directories were already handled just above via revealInExplorer.)
        # 2.1.274 passes a second argument (`{preview:!1}` for pinned tabs):
        #   w$.window.showTextDocument(W,G).then((K)=>{if(Q?.searchText){...
        # `opt` keeps it (with the comma) on the rewritten call.
        "find": re.compile(
            r'(?<![\w$])(?P<ns>[\w$]+)\.window\.showTextDocument\('
            r'(?P<uri>[\w$]+)(?P<opt>,[\w$]+)?\)\.then\(\((?P<cb>[\w$]+)\)=>\{'
            r'(?P<body>if\([\w$]+\?\.searchText\)\{let [\w$]+=(?P=cb)\.document,)'
        ),
        # Rewritten shape:
        #   if(/\.(png|...|pdf)$/i.test(X.fsPath)){_$.commands.executeCommand("vscode.open",X);return}
        #   _$.window.showTextDocument(X[,opts]).catch(()=>{_$.commands.executeCommand("vscode.open",X)})
        #     .then((z)=>{if(!z)return; ...original reveal-range body... })
        "replace": lambda m: (
            f'if(/\\.(png|jpe?g|gif|webp|bmp|ico|avif|svg|mp4|webm|mov|m4v|ogv|mkv|'
            f'mp3|wav|ogg|oga|m4a|flac|aac|pdf)$/i.test({m.group("uri")}.fsPath)){{'
            f'{m.group("ns")}.commands.executeCommand("vscode.open",{m.group("uri")});return}}'
            f'{m.group("ns")}.window.showTextDocument({m.group("uri")}{m.group("opt") or ""})'
            f'.catch(()=>{{{m.group("ns")}.commands.executeCommand("vscode.open",{m.group("uri")})}})'
            f'.then(({m.group("cb")})=>{{if(!{m.group("cb")})return;{m.group("body")}'
        ),
        "already": re.compile(
            r'\.test\([\w$]+\.fsPath\)\)\{[\w$]+\.commands\.executeCommand\("vscode\.open",[\w$]+\);return\}'
            r'[\w$]+\.window\.showTextDocument\([\w$]+(?:,[\w$]+)?\)\.catch\('
        ),
    },
]


def _apply_patch(p, text):
    """One patch on one bundle text -> (new_text, status). Drop-in for the
    inner loop of patch_file(): adds `context` support (replace(match, ctx))."""
    alts = p.get("alts") or [(p["find"], p["replace"], p["already"])]
    ctx = None
    if "context" in p:
        ctx = p["context"](text)
        if ctx is None and not any(a[2].search(text) for a in alts):
            return text, "NOT FOUND (context anchors; verify manually)"
    for find, replace, _already in alts:
        if ctx is not None and callable(replace):
            def rep(m, _r=replace, _c=ctx):
                return _r(m, _c)
        else:
            rep = replace
        patched, n = find.subn(rep, text)
        if n > 0:
            return patched, f"patched ({n})"
    if any(already.search(text) for _f, _r, already in alts):
        return text, "already patched"
    return text, "NOT FOUND (verify manually)"


def main(argv):
    check = "--check" in argv
    by_target = {}
    for p in PATCH_7:
        by_target.setdefault(p["target"], []).append(p)
    rc = 0
    for target, patches in by_target.items():
        for js in skill_patch.find_bundles(target):
            text = js.read_text(encoding="utf-8", errors="surrogatepass")
            new = text
            print(f"\n{js}")
            for p in patches:
                new, status = _apply_patch(p, new)
                mark = {"patched": "✔", "already": "•"}.get(status.split()[0], "✗")
                print(f"  {mark} {p['name']}: {status}")
                if "NOT FOUND" in status:
                    rc = 2
            if new != text and not check:
                bak = js.with_name(js.name + ".prepatch-bak")
                if not bak.exists():
                    bak.write_text(text, encoding="utf-8", errors="surrogatepass")
                js.write_text(new, encoding="utf-8", errors="surrogatepass")
                print(f"  -> written (backup: {bak})")
            elif new != text:
                print("  -> (dry run, not written)")
    print("\nReload the IDE window (Cmd/Ctrl+Shift+P -> 'Reload Window') for changes to take effect.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
