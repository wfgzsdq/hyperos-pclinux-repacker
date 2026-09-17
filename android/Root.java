package local.pclinux.vscode;
import java.io.*;
final class Root {
 static String path;
 static synchronized String find()throws Exception{
  if(path!=null)return path;
  for(String p:new String[]{"su","/debug_ramdisk/su","/sbin/su","/system/bin/su","/product/bin/su"})try{
   Process x=new ProcessBuilder(p,"-c","id -u").redirectErrorStream(true).start();
   if(!x.waitFor(20,java.util.concurrent.TimeUnit.SECONDS)){x.destroy();continue;}
   String result=new String(read(x.getInputStream()),"UTF-8").trim();if(x.exitValue()==0&&result.equals("0")){path=p;return p;}
  }catch(IOException ignored){}
  throw new IOException("未取得 root。请把本应用加入隐藏 root 模块许可范围，并授权。");
 }
 static byte[] read(InputStream in)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[16384];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return out.toByteArray();}
 static String run(String command)throws Exception{
  Process p=new ProcessBuilder(find(),"-M","-c",command).redirectErrorStream(true).start();String result=new String(read(p.getInputStream()),"UTF-8");if(p.waitFor()!=0)throw new IOException(result);return result;
 }
 static void send(String command,String input)throws Exception{
  Process p=new ProcessBuilder(find(),"-M","-c",command).redirectErrorStream(true).start();
  try(OutputStream out=p.getOutputStream()){out.write(input.getBytes("UTF-8"));}
  if(!p.waitFor(30,java.util.concurrent.TimeUnit.SECONDS)){p.destroy();throw new IOException("Callback launch timed out");}
  if(p.exitValue()!=0)throw new IOException("Callback launch failed");
 }
}
