import csv,sys
mark=int(open(sys.argv[1]+"/g13.mark").read())
rows=[r for r in list(csv.reader(open(sys.argv[1]+"/g13_monitor.csv")))[mark-1:] if r and r[0][:1].isdigit() and len(r)==8]
col=lambda i:[float(r[i]) for r in rows]
print("samples",len(rows),"| max worker sessions",max(col(1)),"| max idle_in_tx",max(col(2)),"| max xact age ms",max(col(3)),"| max active",max(col(4)))
print("mem peak MiB %.0f | mem current max MiB %.0f"%(max(col(6))/2**20,max(col(5))/2**20))
cpu=col(7); ts=col(0); busy=[i for i in range(1,len(cpu)) if cpu[i]-cpu[i-1]>5e4]
print("cpu seconds used %.1f over %.1f s => avg %.2f cores"%((cpu[-1]-cpu[0])/1e6, ts[-1]-ts[0], (cpu[-1]-cpu[0])/1e6/(ts[-1]-ts[0])))
print("sessions with xact age > 1000 ms:", sum(1 for r in rows if float(r[3])>1000))
