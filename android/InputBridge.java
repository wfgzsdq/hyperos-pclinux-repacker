package local.pclinux.vscode;

import android.text.*;
import android.view.*;
import android.view.inputmethod.*;
import android.util.Log;

/** Android IME composition stays local until commit; native keys use the RDP path. */
final class InputBridge extends BaseInputConnection {
    private final MainActivity app;
    private final View target;
    InputBridge(MainActivity a, View v) { super(v,true); app=a; target=v; reset(); }
    private void reset() {
        Editable e=getEditable(); e.clear(); e.append(" "); Selection.setSelection(e,1);
        app.imm().updateSelection(target,1,1,-1,-1);
    }
    private boolean composing() { return getComposingSpanStart(getEditable())>=0; }
    @Override public boolean commitText(CharSequence text,int position) {
        app.text(text.toString()); reset(); return true;
    }
    @Override public boolean finishComposingText() {
        // A cancelled composing sequence must not leak into the Linux document.
        super.finishComposingText(); reset(); return true;
    }
    @Override public boolean deleteSurroundingText(int before,int after) {
        if(composing()) return super.deleteSurroundingText(before,after);
        Log.i("PCLinuxInput","IME delete before="+before+" after="+after);
        for(int i=0;i<Math.min(before,256);i++){app.key(8,true);app.key(8,false);}
        for(int i=0;i<Math.min(after,256);i++){app.key(302,true);app.key(302,false);}
        reset();return true;
    }
    @Override public boolean deleteSurroundingTextInCodePoints(int before,int after) {
        return deleteSurroundingText(before,after);
    }
    @Override public boolean sendKeyEvent(KeyEvent event) { return app.forwardKey(event); }
    @Override public boolean performEditorAction(int action) {app.key(13,true);app.key(13,false);return true;}
}
