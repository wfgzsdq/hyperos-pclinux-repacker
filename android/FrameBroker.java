package local.pclinux.vscode;
import java.io.*;import java.nio.*;import java.nio.channels.*;
/** Root worker: only reads UUID-named Xiaomi framebuffer files. No shell input. */
public class FrameBroker {
 public static void main(String[] args)throws Exception{
  DataInputStream in=new DataInputStream(System.in);DataOutputStream out=new DataOutputStream(System.out);
  RandomAccessFile file=null;String last="";byte[] row=new byte[65536];
  while(true){String name;try{name=in.readUTF();}catch(EOFException e){break;}
   int stride=in.readInt(),x=in.readInt(),y=in.readInt(),w=in.readInt(),h=in.readInt();
   try{
    if(!name.matches("\\{[a-fA-F0-9-]{36}\\}")||stride<4||stride>65536||x<0||y<0||w<1||h<1||w>16384||h>16384||(long)(x+w)*4>stride)throw new IOException("Invalid frame");
    if(!last.equals(name)){if(file!=null)file.close();file=new RandomAccessFile("/dev/msl/rdp/"+name,"r");last=name;}
    if((long)(y+h-1)*stride+(long)(x+w)*4>file.length())throw new IOException("Frame bounds");
    out.writeInt(w*h*4);
    for(int j=0;j<h;j++){file.seek((long)(y+j)*stride+x*4L);file.readFully(row,0,w*4);out.write(row,0,w*4);}out.flush();
   }catch(Exception e){out.writeInt(-1);out.writeUTF(e.toString());out.flush();}
  }
  if(file!=null)file.close();
 }
}
