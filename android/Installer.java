package local.pclinux.vscode;
import java.io.*;import java.security.*;import org.json.*;
final class Installer{
 static String hash(File f)throws Exception{MessageDigest md=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(f)){byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1)md.update(b,0,n);}StringBuilder s=new StringBuilder();for(byte b:md.digest())s.append(String.format("%02x",b&255));return s.toString();}
 static File asset(MainActivity a,String name)throws Exception{File f=new File(a.getFilesDir(),name);try(InputStream in=a.getAssets().open(name);OutputStream out=new FileOutputStream(f)){byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}return f;}
 static void start(MainActivity a)throws Exception{
  JSONObject cfg;try(InputStream in=a.getAssets().open("app.json")){cfg=new JSONObject(new String(Root.read(in),"UTF-8"));}
  a.say("正在检查 root 和 Linux 环境…");Root.find();String expected=cfg.getString("image_sha256");
  String exists=Root.run("test -f "+MainActivity.quote(cfg.getString("image_path"))+" && echo present || true");
  File img=new File(a.getFilesDir(),"application.erofs");
  if(!exists.contains("present")){a.say("首次部署：正在展开应用镜像…");asset(a,"application.erofs");a.say("正在校验镜像…");if(!hash(img).equals(expected))throw new IOException("镜像 SHA-256 不匹配");}
  File deploy=asset(a,"deploy.sh"),launch=asset(a,"launch.sh"),opener=asset(a,"open-browser.py"),xdg=asset(a,"xdg-open");a.say("正在挂载并启动 Linux 应用…");
  Root.run("/system/bin/sh "+MainActivity.quote(deploy.getAbsolutePath())+" "+MainActivity.quote(img.getAbsolutePath())+" "+MainActivity.quote(launch.getAbsolutePath())+" "+MainActivity.quote(new File(a.getFilesDir(),"browser-bridge.json").getAbsolutePath())+" "+MainActivity.quote(opener.getAbsolutePath())+" "+MainActivity.quote(xdg.getAbsolutePath()));
  if(img.exists())img.delete();a.say("Linux 应用已启动");
 }
}
