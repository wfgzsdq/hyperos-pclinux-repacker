package local.pclinux.vscode;

import android.content.*;
import android.net.Uri;
import android.util.Log;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import org.json.*;

/** App-scoped, authenticated loopback handoff; no root commands arrive over the socket. */
final class BrowserBridge implements Closeable {
    private final MainActivity app;
    private final ServerSocket listener;
    private final String token;
    private volatile boolean alive=true;
    BrowserBridge(MainActivity a)throws Exception {
        app=a;byte[] random=new byte[32];new SecureRandom().nextBytes(random);
        StringBuilder t=new StringBuilder();for(byte b:random)t.append(String.format("%02x",b&255));token=t.toString();
        listener=new ServerSocket(0,8,InetAddress.getByName("127.0.0.1"));
        JSONObject cfg=new JSONObject();cfg.put("port",listener.getLocalPort());cfg.put("token",token);
        try(FileOutputStream out=new FileOutputStream(new File(app.getFilesDir(),"browser-bridge.json"))){out.write(cfg.toString().getBytes(StandardCharsets.UTF_8));}
        new Thread(()->{while(alive){try(Socket client=listener.accept()){serve(client);}catch(Exception e){if(alive)Log.w("PCLinuxBrowser","Rejected bridge request: "+e.getClass().getSimpleName());}}},"browser-bridge").start();
    }
    static Uri webUri(String value) {
        if(value==null||value.length()>32768||value.indexOf('\r')>=0||value.indexOf('\n')>=0)throw new IllegalArgumentException("Invalid URL");
        Uri u=Uri.parse(value);String s=u.getScheme();
        if(!("https".equalsIgnoreCase(s)||"http".equalsIgnoreCase(s))||u.getHost()==null||u.getUserInfo()!=null)throw new IllegalArgumentException("Only HTTP(S) URLs can open in the browser");
        return u;
    }
    void open(String value) {
        final Uri uri=webUri(value);
        app.runOnUiThread(()->{try {
            Intent i=new Intent(Intent.ACTION_VIEW,uri);i.addCategory(Intent.CATEGORY_BROWSABLE);
            app.startActivity(i);
            Log.i("PCLinuxBrowser","Opened host browser: "+uri.getScheme()+"://"+uri.getHost());
        }catch(ActivityNotFoundException e){app.say("请先安装或启用 Android 浏览器");}});
    }
    private static String line(InputStream in)throws Exception {
        ByteArrayOutputStream b=new ByteArrayOutputStream();int c;
        while((c=in.read())!=-1&&c!='\n'){if(c!='\r')b.write(c);if(b.size()>4096)throw new IOException("Header too long");}
        if(c==-1)throw new EOFException();return b.toString("US-ASCII");
    }
    private void serve(Socket client)throws Exception {
        client.setSoTimeout(5000);InputStream in=client.getInputStream();String first=line(in),auth="";int length=-1;
        for(int n=0;n<40;n++){String h=line(in);if(h.isEmpty())break;int p=h.indexOf(':');if(p<0)throw new IOException("Bad header");String k=h.substring(0,p).trim(),v=h.substring(p+1).trim();if(k.equalsIgnoreCase("Content-Length"))length=Integer.parseInt(v);if(k.equalsIgnoreCase("Authorization"))auth=v;if(n==39)throw new IOException("Too many headers");}
        boolean allowed=first.equals("POST /open HTTP/1.1")&&MessageDigest.isEqual(auth.getBytes(StandardCharsets.UTF_8),("Bearer "+token).getBytes(StandardCharsets.UTF_8));
        String status="403 Forbidden";
        if(allowed&&length>0&&length<=65536){byte[] data=new byte[length];new DataInputStream(in).readFully(data);try{String url=new JSONObject(new String(data,StandardCharsets.UTF_8)).getString("url");open(url);status="204 No Content";}catch(Exception e){status="400 Bad Request";}}
        client.getOutputStream().write(("HTTP/1.1 "+status+"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));
    }
    public void close()throws IOException{alive=false;listener.close();}
}
