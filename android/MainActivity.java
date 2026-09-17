package local.pclinux.vscode;
import android.app.*;import android.os.*;import android.content.*;import android.widget.*;import android.util.Log;import android.view.*;import android.view.inputmethod.*;import android.graphics.*;import java.io.*;import java.nio.*;import java.util.*;
public class MainActivity extends Activity {
 static final String SERVER="com.xiaomi.baselibrary.multiwindow.IServer",CLIENT="com.xiaomi.baselibrary.multiwindow.IAppClient";
 IBinder server;volatile long session;TextView status;Desktop screen;volatile boolean alive=true;boolean bound;boolean announced;
 boolean resumed, textActive, deployed; int activeWindow=-1,mainWindow=-1; Desktop inputTarget; BrowserBridge browser; String pendingUrl; final Map<Integer,NativeDialog> dialogs=new HashMap<>();
 final java.util.concurrent.ExecutorService inputQueue=java.util.concurrent.Executors.newSingleThreadExecutor();
 java.lang.Process broker;DataInputStream bin;DataOutputStream bout;
 final LinkedHashMap<Integer,Frame> windows=new LinkedHashMap<>();final Object framesLock=new Object();
 static class Frame{int id,x,y,w,h,stride;String name;boolean popup,modal,dirty=true;Bitmap bitmap;byte[] pixels;}
 void say(String s){Log.i("PCLinux",s);runOnUiThread(()->status.setText(s));}
 interface Write{void put(Parcel p);}
 void call(int code,Write write){if(server==null)return;Parcel d=Parcel.obtain(),r=Parcel.obtain();try{d.writeInterfaceToken(SERVER);write.put(d);server.transact(code,d,r,0);r.readException();}catch(Exception e){Log.e("PCLinux","Binder",e);}finally{d.recycle();r.recycle();}}
 void key(int vk,boolean down){if(!alive)return;inputQueue.execute(()->{call(4,p->{p.writeLong(session);p.writeInt(vk);p.writeInt(down?1:0);});try{Thread.sleep(12);}catch(InterruptedException ignored){}});}
 void rawKey(int vk,boolean down){call(4,p->{p.writeLong(session);p.writeInt(vk);p.writeInt(down?1:0);});try{Thread.sleep(12);}catch(InterruptedException ignored){}}
 int charKey(char c){if(c>='a'&&c<='z')return c-32;if(c>='A'&&c<='Z'||c>='0'&&c<='9')return c;switch(c){case ' ':return 32;case '\n':return 13;case '\t':return 9;case '-':case '_':return 189;case '=':case '+':return 187;case '[':case '{':return 219;case ']':case '}':return 221;case '\\':case '|':return 220;case ';':case ':':return 186;case '\'':case '"':return 222;case ',':case '<':return 188;case '.':case '>':return 190;case '/':case '?':return 191;case '`':case '~':return 192;}String shifted=")!@#$%^&*(";int n=shifted.indexOf(c);return n>=0?48+n:0;}
 void text(String s){inputQueue.execute(()->{if(s.chars().anyMatch(c->c>127)){rawKey(300,true);call(8,p->p.writeString(s));try{Thread.sleep(100);}catch(InterruptedException ignored){}rawKey(300,false);return;}rawKey(160,false);rawKey(162,false);rawKey(164,false);for(int i=0;i<s.length();i++){char c=s.charAt(i);int v=charKey(c);if(v!=0){boolean shift=c>='A'&&c<='Z'||"~!@#$%^&*()_+{}|:\"<>?".indexOf(c)>=0;if(shift)rawKey(160,true);rawKey(v,true);rawKey(v,false);if(shift)rawKey(160,false);}else{String value=String.valueOf(c);if(Character.isHighSurrogate(c)&&i+1<s.length())value+=s.charAt(++i);final String committed=value;rawKey(300,true);call(8,p->p.writeString(committed));try{Thread.sleep(90);}catch(InterruptedException ignored){}rawKey(300,false);}}});}
 void mouse(int x,int y,int flags){call(3,p->{p.writeLong(session);p.writeInt(x);p.writeInt(y);p.writeInt(flags);});}
 void focus(int id){call(10,p->{p.writeLong(session);p.writeInt(id);p.writeInt(1);p.writeInt(0);});}
 final Binder callback=new Binder(){protected boolean onTransact(int code,Parcel d,Parcel r,int flags)throws RemoteException{
  if(code==INTERFACE_TRANSACTION){r.writeString(CLIENT);return true;}d.enforceInterface(CLIENT);
  if(code==1){session=d.readLong();say("显示服务已连接");}
  else if(code==3){d.readLong();int[] a=new int[10];for(int i=0;i<10;i++)a[i]=d.readInt();String name=d.readString();int size=d.readInt();boolean pop=d.readInt()!=0;d.readInt();int type=d.readInt();boolean modal=d.readInt()!=0;d.readInt();
   if(type==0&&a[3]>0&&a[4]>0&&(long)a[3]*a[4]<=16000000&&a[9]>=a[3]*4){synchronized(framesLock){Frame f=windows.get(a[0]);if(f==null){if(windows.size()>=12)windows.remove(windows.keySet().iterator().next());f=new Frame();f.id=a[0];windows.put(f.id,f);Log.i("PCLinux","window="+f.id+" "+a[3]+"x"+a[4]);}f.x=a[1];f.y=a[2];f.w=a[3];f.h=a[4];f.stride=a[9];f.name=name;f.popup=pop;f.modal=modal;f.dirty=true;runOnUiThread(()->syncNativeWindows());}}}
  else if(code==4){d.readLong();int id=d.readInt();synchronized(framesLock){windows.remove(id);}runOnUiThread(()->{NativeDialog dialog=dialogs.remove(id);if(dialog!=null)dialog.dismiss();if(mainWindow==id)mainWindow=-1;syncNativeWindows();if(activeWindow==id&&mainWindow>=0)windowFocus(mainWindow,screen);});screen.postInvalidate();}
  else if(code==6){boolean activate=d.readInt()!=0;runOnUiThread(()->inputActivated(activate));}
  else if(code==8){int type=d.readInt(),x=d.readInt(),y=d.readInt(),w=d.readInt(),h=d.readInt();runOnUiThread(()->{if(inputTarget!=null){inputTarget.cursor=new Rect(x,y,x+w,y+h);inputTarget.invalidate();}});}
  else if(code==14){String url=d.readString();if(browser!=null)try{browser.open(url);}catch(Exception e){Log.w("PCLinuxBrowser","Rejected framework URL");}}
  else if(code==5){d.readLong();int type=d.readInt();boolean minimized=d.readInt()!=0;if(type==0&&minimized)runOnUiThread(()->moveTaskToBack(true));}
  if(r!=null)r.writeNoException();return true;
 }};
 ServiceConnection connection=new ServiceConnection(){public void onServiceConnected(ComponentName n,IBinder b){server=b;call(1,p->{p.writeStrongBinder(callback);p.writeInt(0);});say("已注册 Linux 窗口");}public void onServiceDisconnected(ComponentName n){server=null;say("显示服务已断开，请重新打开应用");}};
 static String quote(String s){return "'"+s.replace("'","'\\''")+"'";}
 void worker(){try{
  say("正在申请 root 并连接画面…");
  broker=new ProcessBuilder(Root.find(),"-M","-c","CLASSPATH="+quote(getApplicationInfo().sourceDir)+" /system/bin/app_process /system/bin local.pclinux.vscode.FrameBroker").start();
  new Thread(()->{try{BufferedReader e=new BufferedReader(new InputStreamReader(broker.getErrorStream()));String s;while((s=e.readLine())!=null)Log.e("PCLinuxBroker",s);}catch(Exception ignored){}}).start();
  bin=new DataInputStream(new BufferedInputStream(broker.getInputStream(),262144));bout=new DataOutputStream(broker.getOutputStream());
  int lastFrame=-1;
  while(alive){Frame target=null;String name=null;int w=0,h=0,stride=0;
   synchronized(framesLock){List<Frame> frames=new ArrayList<>(windows.values());int start=0;for(int i=0;i<frames.size();i++)if(frames.get(i).id==lastFrame)start=i+1;for(int i=0;i<frames.size();i++){Frame f=frames.get((start+i)%frames.size());if(f.dirty){target=f;lastFrame=f.id;name=f.name;w=f.w;h=f.h;stride=f.stride;f.dirty=false;break;}}}
   if(target==null){Thread.sleep(40);continue;}
   bout.writeUTF(name);bout.writeInt(stride);bout.writeInt(0);bout.writeInt(0);bout.writeInt(w);bout.writeInt(h);bout.flush();
   int length=bin.readInt();if(length<0){Log.w("PCLinux",bin.readUTF());synchronized(framesLock){windows.remove(target.id);}continue;}if(length!=w*h*4)throw new IOException("Invalid frame length");
   if(target.pixels==null||target.pixels.length!=length)target.pixels=new byte[length];bin.readFully(target.pixels);
   synchronized(framesLock){if(target.bitmap==null||target.bitmap.getWidth()!=w||target.bitmap.getHeight()!=h)target.bitmap=Bitmap.createBitmap(w,h,Bitmap.Config.ARGB_8888);target.bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(target.pixels));}
   runOnUiThread(()->{screen.invalidate();for(NativeDialog dialog:dialogs.values())dialog.desktop.invalidate();});if(!announced){say("运行中 · Linux ARM64");announced=true;}Thread.sleep(70);
  }
 }catch(Exception e){say("画面连接失败："+e+"。请允许此应用使用 root。");}}
 public void onCreate(Bundle b){super.onCreate(b);getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);status=new TextView(this);status.setTextSize(12);screen=new Desktop(-1);inputTarget=screen;try{browser=new BrowserBridge(this);}catch(Exception e){say("浏览器桥接初始化失败");}receiveIntent(getIntent());
  LinearLayout layout=new LinearLayout(this);layout.setOrientation(1);LinearLayout bar=new LinearLayout(this);Button keyboard=new Button(this);keyboard.setText("键盘");keyboard.setFocusable(false);keyboard.setOnClickListener(v->{if(inputTarget==null)inputTarget=screen;showKeyboard(true);});bar.addView(keyboard);bar.addView(status,new LinearLayout.LayoutParams(0,-2,1));layout.addView(bar);layout.addView(screen,new LinearLayout.LayoutParams(-1,0,1));setContentView(layout);
  Intent i=new Intent();i.setComponent(new ComponentName("com.xiaomi.mslgrdp","com.xiaomi.mslgrdp.multwindow.MultiWindowService"));try{bound=bindService(i,connection,BIND_AUTO_CREATE);say("bind="+bound);}catch(Exception e){say(e.toString());}
  new Thread(()->{try{Installer.start(this);deployed=true;deliverPendingUrl();worker();}catch(Exception e){say("启动失败："+e.getMessage());}},"frame-reader").start();
 }
 protected void onDestroy(){alive=false;call(2,p->{p.writeStrongBinder(callback);p.writeInt(0);});if(bound)unbindService(connection);if(broker!=null)broker.destroy();if(browser!=null)try{browser.close();}catch(Exception ignored){}inputQueue.shutdownNow();for(NativeDialog dialog:new ArrayList<>(dialogs.values()))dialog.dismiss();super.onDestroy();}
 int vk(int k){if(k>=29&&k<=54)return 65+k-29;if(k>=7&&k<=16)return 48+k-7;if(k>=131&&k<=142)return 112+k-131;
  switch(k){case 66:return 13;case 67:return 8;case 61:return 9;case 62:return 32;case 111:return 27;case 112:return 302;case 19:return 294;case 20:return 296;case 21:return 293;case 22:return 295;case 92:return 289;case 93:return 290;case 122:return 292;case 123:return 291;case 124:return 301;case 59:return 160;case 60:return 161;case 113:return 162;case 114:return 163;case 57:return 164;case 58:return 165;case 55:return 188;case 56:return 190;case 69:return 189;case 70:return 187;case 71:return 219;case 72:return 221;case 73:return 220;case 74:return 186;case 75:return 222;case 76:return 191;case 68:return 192;}return 0;}
 android.view.inputmethod.InputMethodManager imm(){return (InputMethodManager)getSystemService(INPUT_METHOD_SERVICE);}
 boolean hardwareKeyboard(){for(int id:InputDevice.getDeviceIds()){InputDevice d=InputDevice.getDevice(id);if(d!=null&&!d.isVirtual()&&d.getKeyboardType()==InputDevice.KEYBOARD_TYPE_ALPHABETIC)return true;}return false;}
 void showKeyboard(boolean forced){if(inputTarget==null||!resumed)return;inputTarget.requestFocus();if(forced||!hardwareKeyboard())imm().showSoftInput(inputTarget,InputMethodManager.SHOW_IMPLICIT);}
 void inputActivated(boolean active){textActive=active;Log.i("PCLinuxInput","Native text focus="+active+" window="+activeWindow);if(active)showKeyboard(false);else if(inputTarget!=null)imm().hideSoftInputFromWindow(inputTarget.getWindowToken(),0);}
 void syncNativeWindows(){List<Frame> additional=new ArrayList<>();synchronized(framesLock){
  if(!windows.containsKey(mainWindow)){mainWindow=-1;for(Frame f:windows.values())if(!f.popup&&!f.modal){mainWindow=f.id;break;}}
  screen.windowId=mainWindow;
  for(Frame f:windows.values())if(!f.popup&&f.id!=mainWindow&&!dialogs.containsKey(f.id))additional.add(f);
 }for(Frame f:additional){NativeDialog dialog=new NativeDialog(f);dialogs.put(f.id,dialog);dialog.show();}screen.invalidate();}
 void windowFocus(int id,Desktop view){activeWindow=id;inputTarget=view;view.requestFocus();focus(id);}
 boolean preImeKey(KeyEvent e){int k=e.getKeyCode();if(e.isCtrlPressed()||e.isAltPressed()||k==113||k==114||k==57||k==58)return forwardKey(e);return false;}
 boolean forwardKey(KeyEvent e){
  if(e.getAction()==KeyEvent.ACTION_MULTIPLE){if(e.getCharacters()!=null)text(e.getCharacters());return true;}
  int code=vk(e.getKeyCode());if(code==0||session==0)return false;
  Log.i("PCLinuxInput","key="+e.getKeyCode()+" action="+e.getAction()+" device="+e.getDeviceId());
  final boolean down=e.getAction()==KeyEvent.ACTION_DOWN;
  inputQueue.execute(()->{if(down&&(code<160||code>165)){rawKey(162,e.isCtrlPressed());rawKey(164,e.isAltPressed());rawKey(160,e.isShiftPressed());}rawKey(code,down);});return true;
 }
 @Override public boolean dispatchKeyEvent(KeyEvent e){return forwardKey(e)||super.dispatchKeyEvent(e);}
 @Override protected void onResume(){super.onResume();resumed=true;if(activeWindow>=0)focus(activeWindow);}
 @Override protected void onPause(){resumed=false;if(alive)inputQueue.execute(()->{for(int k:new int[]{160,161,162,163,164,165})rawKey(k,false);});super.onPause();}
 @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);receiveIntent(intent);if(deployed)new Thread(()->deliverPendingUrl(),"login-return").start();}
 synchronized void receiveIntent(Intent intent){if(intent!=null&&Intent.ACTION_VIEW.equals(intent.getAction())){android.net.Uri u=intent.getData();if(u!=null&&"vscode".equals(u.getScheme())&&u.toString().length()<=32768&&u.toString().indexOf('\n')<0&&u.toString().indexOf('\r')<0){pendingUrl=u.toString();Log.i("PCLinuxBrowser","Received vscode callback");}}}
 synchronized void deliverPendingUrl(){String uri=pendingUrl;if(uri==null)return;pendingUrl=null;try{
  // Keep authorization data out of the root request command and its policy log.
  String command="IFS= read -r callback; nohup /opt/pclinux/vscode/launch.sh --open-url \"$callback\" >/dev/null 2>&1 </dev/null &";
  Root.send("/vendor/bin/chroot /data/rootfs /bin/su -s /bin/sh product_hyperengine -c "+quote(command),uri+"\n");
  Log.i("PCLinuxBrowser","Forwarded vscode callback to Linux");
 }catch(Exception e){say("登录回调转发失败，请重试登录");}}
 class NativeDialog extends Dialog{
  Desktop desktop;int id;
  NativeDialog(Frame f){super(MainActivity.this,android.R.style.Theme_Material_Light_Dialog_NoActionBar);id=f.id;desktop=new Desktop(id);setContentView(desktop);setCanceledOnTouchOutside(false);}
  @Override public void show(){super.show();Window w=getWindow();w.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING);w.clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);Rect bounds=getWindowManager().getCurrentWindowMetrics().getBounds();Frame f; synchronized(framesLock){f=windows.get(id);}if(f!=null)w.setLayout(Math.min(f.w,bounds.width()),Math.min(f.h,bounds.height()-120));windowFocus(id,desktop);}
  @Override public boolean dispatchKeyEvent(KeyEvent e){return forwardKey(e)||super.dispatchKeyEvent(e);}
  @Override public void onBackPressed(){call(9,p->{p.writeLong(session);p.writeInt(id);p.writeInt(0xf060);});}
 }
 class Desktop extends View{
  float scale=1,ox=0,oy=0;Frame primary;Paint paint=new Paint(3);int windowId;Rect cursor;int imeHeight;String lastGeometry="";
  Desktop(int id){super(MainActivity.this);windowId=id;setFocusable(true);setFocusableInTouchMode(true);setBackgroundColor(Color.rgb(25,25,25));
   setOnApplyWindowInsetsListener((v,insets)->{imeHeight=insets.isVisible(WindowInsets.Type.ime())?insets.getInsets(WindowInsets.Type.ime()).bottom:0;invalidate();return insets;});
  }
  protected void onDraw(Canvas c){synchronized(framesLock){primary=windows.get(windowId);if(primary==null||primary.bitmap==null)return;
   scale=Math.min(getWidth()/(float)primary.w,getHeight()/(float)primary.h);ox=(getWidth()-primary.w*scale)/2;oy=(getHeight()-primary.h*scale)/2;
   if(imeHeight>0&&cursor!=null){float bottom=(cursor.bottom-primary.y)*scale+oy;float visible=getHeight()-imeHeight-24;oy-=Math.max(0,bottom-visible);}
   String geometry=getWidth()+"x"+getHeight()+" scale="+scale+" ime="+imeHeight;
   if(!geometry.equals(lastGeometry)){lastGeometry=geometry;Log.i("PCLinuxGeometry",geometry);}
   draw(c,primary);if(activeWindow==primary.id||activeWindow<0)for(Frame f:windows.values())if(f.popup&&f.bitmap!=null)draw(c,f);
  }}
  void draw(Canvas c,Frame f){float x=ox+(f.x-primary.x)*scale,y=oy+(f.y-primary.y)*scale;c.drawBitmap(f.bitmap,null,new RectF(x,y,x+f.w*scale,y+f.h*scale),paint);}
  public boolean onTouchEvent(MotionEvent e){if(primary==null)return true;int x=(int)((e.getX()-ox)/scale)+primary.x,y=(int)((e.getY()-oy)/scale)+primary.y;int a=e.getActionMasked();
   if(a==0){windowFocus(primary.id,this);mouse(x,y,0x800);mouse(x,y,0x9000);}else if(a==1||a==3){mouse(x,y,0x1000);if(textActive)postDelayed(()->showKeyboard(false),100);}else if(a==2)mouse(x,y,0x800);return true;}
  public boolean onGenericMotionEvent(MotionEvent e){if(primary==null)return false;int x=(int)((e.getX()-ox)/scale)+primary.x,y=(int)((e.getY()-oy)/scale)+primary.y;if(e.getAction()==MotionEvent.ACTION_SCROLL){mouse(x,y,e.getAxisValue(MotionEvent.AXIS_VSCROLL)>0?0x278:0x388);return true;}if(e.getAction()==MotionEvent.ACTION_HOVER_MOVE){mouse(x,y,0x800);return true;}return super.onGenericMotionEvent(e);}
  @Override public boolean onKeyPreIme(int k,KeyEvent e){return preImeKey(e)||super.onKeyPreIme(k,e);}
  @Override public void onWindowFocusChanged(boolean hasFocus){super.onWindowFocusChanged(hasFocus);if(hasFocus&&textActive)post(()->showKeyboard(false));}
  public boolean onCheckIsTextEditor(){return true;}
  public InputConnection onCreateInputConnection(EditorInfo info){info.inputType=android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS;info.initialSelStart=info.initialSelEnd=1;info.imeOptions=EditorInfo.IME_FLAG_NO_EXTRACT_UI|EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING;return new InputBridge(MainActivity.this,this);}
 }
}
