from tkcalendar import Calendar
from tkinter import *
from tkinter import ttk

from PIL import ImageTk, Image
import sqlite3
import datetime as dt
from tkinter import messagebox 
from datetime import date
from tkinter import Listbox





# Create a window
anapencere = Toplevel()

ico = Image.open('C:/Users/Admin/Downloads/SC.ico')
photo = ImageTk.PhotoImage(ico)
anapencere.wm_iconphoto(False, photo)

anapencere.title("SocialCircle")
anapencere.config(bg="#f0f2f5")  # Light background for modern look
vt = sqlite3.connect('C:/Users/Admin/Python/kullanicilar2.sqlite')  # Veritabanı dosya yolunu düzenleyin
tt = sqlite3.connect('C:/Users/Admin/Python/etkinlikler3.sqlite')  # Veritabanı dosya yolunu düzenleyin

def uye_kaydi_ac():

    uyegirisi_pencere = Toplevel()
    baslik = Label(uyegirisi_pencere, text="Üye girisi")
    baslik.pack()
    #anapencere.withdraw()
    uyegirisi_pencere.geometry("1024x1024")
    # Giriş kısmı
    giris_label = ttk.Label(uyegirisi_pencere, text="Giriş", font=("Segoe UI", 18, "bold"), foreground="#333")
    giris_label.pack(pady=20)
        # Kullanıcı adı etiketi ve giriş alanı
    kullanici_label = ttk.Label(uyegirisi_pencere, text="Kullanıcı Adı:", font=("Segoe UI", 12))
    kullanici_label.pack(pady=(10, 0))
    kullanici_entry = ttk.Entry(uyegirisi_pencere, font=("Segoe UI", 12))
    kullanici_entry.pack(pady=(0, 10), ipadx=5, ipady=5)
    # Parola etiketi ve giriş alanı
    parola_label = ttk.Label(uyegirisi_pencere, text="Parola:", font=("Segoe UI", 12))
    parola_label.pack(pady=(10, 0))
    parola_entry = ttk.Entry(uyegirisi_pencere, show="*", font=("Segoe UI", 12))
    parola_entry.pack(pady=(0, 10), ipadx=5, ipady=5)
    
    # Sonuç etiketi
    result_label = ttk.Label(uyegirisi_pencere, text="", font=("Segoe UI", 10), foreground="red")
    result_label.pack(pady=12)
    # Giriş düğmesi
    giris_button = ttk.Button(uyegirisi_pencere, text="Giriş", style="Accent.TButton")
    
    giris_button.pack(pady=10, ipadx=10, ipady=5)
    #giris_button(x=500,y=600)


    #tüm resimleri denedin herhangi bir görsel gene çıkmıyor sadece beyaz bir background
    imgcross = Image.open("C:/Users/Admin/Desktop/Python/takım sporları.png")
    img50 = ImageTk.PhotoImage(imgSC)
    imgcross = imgcross.resize((150,150))
    img50 = ImageTk.PhotoImage(imgSC)


    label40 = Label(uyegirisi_pencere, image=img50, bg="#FFFFFF", borderwidth=0)

    label40.place(x=735, y=180)


   


    def login():
        
        # Kullanıcıdan kullanıcı adı ve parolayı alıyoruz
        kull = kullanici_entry.get()
        paro = parola_entry.get()
        
        # Veritabanında kullanıcı adı ve parolayı kontrol ediyoruz 
        im.execute("""SELECT * FROM kullanicilar2 WHERE
        kullanici_adi = ? AND parola = ? """,
                (kull, paro,))
        data = im.fetchall()
        # Veritabanından gelen sonuçları kontrol ediyoruz
        
        if data:
            result_label.config(text="Programa hoş geldin " + kull + " :D")
            mainpage = Tk()
            mainpage.title("Main Page")
            etkinlik_button = ttk.Button(mainpage, text="etkinlik ekle", command = etkinlik_olustur)
            etkinlik_button.pack(pady=0)
            etkinlik_button = ttk.Label(mainpage, text = "")
            etkinlik_button.pack()
            mainpage.geometry("1024x768")
            mainpage.resizable(True, True)
            result_label2 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label2.pack(pady=0, padx=500)
            result_label3 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label3.pack(pady=1)
            result_label4 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label4.pack(pady=2)
            result_label5 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label5.pack(pady=3)
            result_label6 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label6.pack(pady=4)
            result_label7 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label7.pack(pady=5)
            result_label8 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label8.pack(pady=6)
            result_label9 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label9.pack(pady=7)
            result_label10 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label10.pack(pady=8)
            result_label11 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label11.pack(pady=9)
            result_label12 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label12.pack(pady=10)
            result_label13 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label13.pack(pady=11)
            result_label14 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label14.pack(pady=12)  
            result_label15 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label15.pack(pady=13)  
            result_label16 = ttk.Label(mainpage, text="", font=("Segoe UI", 10))
            result_label16.pack(pady=14)
            canvas = Canvas(mainpage, width=700, height=500)
            scrollbar = Scrollbar(mainpage, orient="vertical", command=canvas.yview)
            scrollable_frame = Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            def open_filter_window():
                filter_window = Toplevel(mainpage)
                filter_window.title("Filter Activities")
                filter_window.geometry("350x500")

                # Activity Category Filter
                Label(filter_window, text="Filter by Activity Category:").pack(pady=5)
                
                # Define all 13 activity categories
                categories = [
                    "Atletizm", "Jimnastik", "MotorSporlari", "TakimSporlari", 
                    "RaketSporlari", "DovusSporlari", "SuSporlari", "HayvanliSporlar",
                    "ExtremSporlar", "KisSporlari", "TekerlekliSporlar", "HedefSporlari", "ESpor"
                ]

                filter_var = StringVar()
                filter_listbox = Listbox(filter_window, listvariable=filter_var, height=8)
                filter_listbox.pack(padx=10, pady=5, fill=BOTH, expand=True)

                for category in categories:
                    filter_listbox.insert(END, category)

                # City Filter
                Label(filter_window, text="Filter by City:").pack(pady=5)
                
                city_options = [
                    "Adana", "Adıyaman", "Afyonkarahisar", "Aksaray", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", 
                    "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", 
                    "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", 
                    "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir", 
                    "Kahramanmaraş", "Karabük", "Karaman", "Kastamonu", "Kayseri", "Kilis", "Kocaeli", "Konya", "Kütahya", "Malatya", 
                    "Manisa", "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", 
                    "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", 
                    "Yozgat", "Zonguldak"
                ]
                
                city_combo = ttk.Combobox(filter_window, values=city_options, width=25)
                city_combo.pack(pady=5)
                city_combo.set("All Cities")  # Default value

                def apply_filter():
                    selected_category = None
                    selected_city = None
                    
                    # Get selected category
                    category_selection = filter_listbox.curselection()
                    if category_selection:
                        selected_category = filter_listbox.get(category_selection[0])
                    
                    # Get selected city
                    selected_city = city_combo.get()
                    if selected_city == "All Cities":
                        selected_city = None

                    # Clear previous buttons
                    for widget in scrollable_frame.winfo_children():
                        widget.destroy()

                    # Reload buttons with filters applied
                    im2.execute("SELECT * FROM etkinlikler3")
                    rows = im2.fetchall()
                    for row in rows:
                        Etkinlik_listesi = str(row)
                        Etkinlik_listesi_veriler = Etkinlik_listesi.split(',')

                        Etkinlik_bitis_tarihi_str = Etkinlik_listesi_veriler[3].strip().strip("'")
                        try:
                            Etkinlik_bitis_tarihi_date = dt.datetime.strptime(Etkinlik_bitis_tarihi_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue

                        today_date = dt.date.today()
                        if Etkinlik_bitis_tarihi_date < today_date:
                            continue

                        category = Etkinlik_listesi_veriler[4].strip().strip("'")
                        city = Etkinlik_listesi_veriler[7].strip().strip("'")

                        # Apply category filter
                        if selected_category and category != selected_category:
                            continue
                            
                        # Apply city filter
                        if selected_city and city != selected_city:
                            continue

                        # Create button for the event
                        stripped_name = Etkinlik_listesi_veriler[1].strip().strip('"')
                        btn_text = f"{category}: {stripped_name}"
                        event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                        btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                        btn.pack(pady=2)

                # Add Apply button to the filter window
                apply_button = Button(filter_window, text="Apply Filter", command=apply_filter)
                apply_button.pack(pady=5)
                
                # Add Show All button to display all activities
                show_all_button = Button(filter_window, text="Show All", command=lambda: show_all_activities())
                show_all_button.pack(pady=5)
                
                def show_all_activities():
                    # Clear previous buttons
                    for widget in scrollable_frame.winfo_children():
                        widget.destroy()
                    
                    # Reload all activities without any filters
                    im2.execute("SELECT * FROM etkinlikler3")
                    rows = im2.fetchall()
                    for row in rows:
                        Etkinlik_listesi = str(row)
                        Etkinlik_listesi_veriler = Etkinlik_listesi.split(',')
                        
                        Etkinlik_bitis_tarihi_str = Etkinlik_listesi_veriler[3].strip().strip("'")
                        try:
                            Etkinlik_bitis_tarihi_date = dt.datetime.strptime(Etkinlik_bitis_tarihi_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue
                        
                        today_date = dt.date.today()
                        if Etkinlik_bitis_tarihi_date < today_date:
                            continue
                        
                        category = Etkinlik_listesi_veriler[4].strip().strip("'")
                        
                        # Create button for the event
                        stripped_name = Etkinlik_listesi_veriler[1].strip().strip('"')
                        btn_text = f"{category}: {stripped_name}"
                        event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                        btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                        btn.pack(pady=2)

            def show_event_details(event_info):
                detail_window = Toplevel(mainpage)
                detail_window.title("Etkinlik Detayları")
                detail_window.geometry("500x350")
                detail_label = Label(detail_window, text=event_info, justify=LEFT, wraplength=480, font=("Segoe UI", 11))
                detail_label.pack(padx=10, pady=10)

            filter_button = Button(mainpage, text="Filter", width=10, command=open_filter_window)

            # Place the filter button at the left bottom corner over the scrollable listbox
            filter_button.place(x=20, y=480)  # Adjust y coordinate as needed to position at bottom left corner

            canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
            scrollbar.pack(side="right", fill="y")

            # Add mousewheel scrolling support
            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")



            canvas.bind_all("<MouseWheel>", _on_mousewheel)

            # Clear previous buttons if any
            for widget in scrollable_frame.winfo_children():
                widget.destroy()





            
               
            




            #result = "1"
            #result_labelmainpage = ttk.Label (mainpage, text = result )
            #result_labelmainpage.pack(pady = 12)
            im.execute("""SELECT * FROM kullanicilar2 WHERE kullanici_adi = ?;
             """,
                   (kull, ))
            result_label.config(text = data)
            veriler = str(data)
            my_veriler = veriler.split(',')
            #print(my_veriler[7])
            #print(my_veriler[8])
            #print(my_veriler[9])
            data = im.fetchall()
            veridersenkafankarisir = my_veriler[4]
            dogum_gunu = veridersenkafankarisir.split()
            dogum_gunu_bir = dogum_gunu[0].split("-")
            dogum_gunu_ay = dogum_gunu_bir[1]
            dogum_gunu_gun = dogum_gunu_bir[2]  
            today1 = date.today()
            today2 = str(today1)
            todaydizi = today2.split("-")
            print(todaydizi[1],todaydizi[2])
            print (today1) 
            noway = todaydizi[1]
            nowgun = todaydizi[2]
            if (my_veriler[5] == " '1'" ):
              result_label2.config(text = "Atletizm e ilginiz var")
              print ("Atletizm e ilginiz var")
              print(my_veriler[5])
              #imgatletizm = Image.open("C:/Users/Admin/Desktop/Python/atletizim.png")
              #img3 = ImageTk.PhotoImage(imgatletizm)

              #label = Label(mainpage, image=img3)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            if (my_veriler[6] == " '1'" ):
              result_label3.config(text = "Jimnastik e ilginiz var" ,font=("Helvictia", 24 , "bold" ))
              print ("Jimnastik e ilginiz var")
              #imgjimnastik = Image.open("C:/Users/Admin/Desktop/Python/jimnastik.png")
              #img4 = ImageTk.PhotoImage(imgjimnastik)

              #label = Label(mainpage, image=img4)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=200, y=175)

            if (my_veriler[7] == " '1'" ):
              result_label4.config(text = "Motor Sporlarina ilginiz var" ,font=("Helvictia", 24 , "bold" ))
              print ("Motor Sporlarina ilginiz var")
              

              #imgmotor = Image.open("C:/Users/Admin/Desktop/Python/images.png")
              #img5 = ImageTk.PhotoImage(imgmotor)

              #label510 = Label(mainpage, image=img5)
              #label510.pack(side='top left', fill=Y, expand=True)
              #label510.place(x=50, y=175)
              #result_label4.config(img5, text = "Motor sporlarina  ilginiz var")

             # label510 = Label(mainpage, image=img5, bg="#FFFFFF", borderwidth=0)


            if (my_veriler[8] == " '1'" ):
              result_label5.config(text = "Takım sporlarina  ilginiz var")
              #messagebox.showinfo("ilgileriniz", "Takım sporlarina ilginiz var") 
              print ("Takım sporlarina  ilginiz var")
              
              #imgtakim = Image.open("C:/Users/Admin/Desktop/Python/takım sporları.png")
              #img6 = ImageTk.PhotoImage(imgtakim)

              #label = Label(mainpage, image=img6)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)              
            if (my_veriler[9] == " '1'" ):
              result_label6.config(text = "Raket sporlarına ilginiz var")
              print (my_veriler[9])

              #imgraket = Image.open("C:/Users/Admin/Desktop/Python/raket.png")
              #img7 = ImageTk.PhotoImage(imgraket)

              #label = Label(mainpage, image=img7)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            if (my_veriler[10] == " '1'" ):
              result_label7.config(text = "Dövüş spornlarına ilginiz var")
              print (my_veriler[10])
              
              #imgdovus = Image.open("C:/Users/Admin/Desktop/Python/dövüş sporları.png")
              #img8 = ImageTk.PhotoImage(imgdovus)

              #label = Label(mainpage, image=img8)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            
            if (my_veriler[11] == " '1'" ):
              result_label8.config(text = "Su sporlarına ilginiz var")
              #messagebox.showinfo("ilgileriniz", "Su sğprlarına ilginiz var") 
              print (my_veriler[11])

                    # Add SocialCircle label at the top-left corner
                #imgSC = Image.open("C:/Users/Admin/Desktop/Python/SC.png")
            #img1 = ImageTk.PhotoImage(imgSC)
                  #imgSC = imgSC.resize((150,150))
                #img1 = ImageTk.PhotoImage(imgSC)


                #label = Label(anapencere, image=img1, bg="#FFFFFF", borderwidth=0)

                #label.place(x=735, y=180)


              #imgsu = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")      
              #img9 = ImageTk.PhotoImage(imgsu)

              #label = Label(mainpage, image=img9)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=500, y=500)

            if (my_veriler[12] == " '1'" ):
              result_label9.config(text = "Hayvan sporlarına ilginiz var")
              print (my_veriler[12])

              #imghayvan = Image.open("C:/Users/Admin/Desktop/Python/istockphoto-840182132-170667a.png")
              #img10 = ImageTk.PhotoImage(imghayvan)
              #imghayvan = imghayvan.resize((150,150))

              #label = Label(mainpage, image=img10)
              #label.pack(side='middle', fill=Y, expand=True)
              #label.place(x=500, y=500)

            if (my_veriler[13] == " '1'" ):
              result_label10.config(text = "Extrem sporlara ilginiz var")
              print (my_veriler[13])

              #imgextrem = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img11 = ImageTk.PhotoImage(imgextrem)

              #label = Label(mainpage, image=img11)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (my_veriler[14] == " '1'" ):
              result_label11.config(text = "Kış sporlarına ilginiz var")
              print (my_veriler[14])

              #imgkis = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img12 = ImageTk.PhotoImage(imgkis)

              #label = Label(mainpage, image=img12)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (my_veriler[15] == " '1'" ):
              result_label12.config(text = "Tekerlekli sporlara ilginiz var")
              print (my_veriler[15])

              #imgtekerlek = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img13 = ImageTk.PhotoImage(imgtekerlek)

              #label = Label(mainpage, image=img13)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (my_veriler[16] == " '1'" ):
              result_label13.config(text = "Hedef sporlarına ilginiz var")
              print (my_veriler[16])

              #imghedef = Image.open("C:/Users/Admin/Desktop/Python/hedef tahtası.png")
              #img14 = ImageTk.PhotoImage(imghedef)

              #label = Label(mainpage, image=img14)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (my_veriler[17] == " '1')]" ):
              result_label14.config(text = "E-Spor e ilginiz var")
              print (my_veriler[17])

              #imgespor = Image.open("C:/Users/Admin/Desktop/Python/e spor.png")
              #img15 = ImageTk.PhotoImage(imgespor)

              #label = Label(mainpage, image=img15)
              #label.pack(side='top left', fill=Y, expand=True)
             # label.place(x=50, y=175)
            
            if (my_veriler[5] == " '0'" and my_veriler[6] == " '0'" and  my_veriler[7] == " '0'" and  my_veriler[8] == " '0'" and  my_veriler[9] == " '0'" and  my_veriler[10] == " '0'" and  my_veriler[11] == " '0'" and  my_veriler[12] == " '0'" and  my_veriler[13] == " '0'" and  my_veriler[14] == " '0'" and  my_veriler[15] == " '0'" and  my_veriler[16] == " '0'" and  my_veriler[17] == " '0')]"):
              result_label15.config(mainpage,text= "Herhangi bir spora ilginiz yok")

              messagebox.showinfo("ilgileriniz", "Herhangi bir spora ilginiz yok")
            if (dogum_gunu_ay == noway and dogum_gunu_gun == nowgun):
              messagebox.showinfo("Annenizden çıkma yıldönümünüz mübarek olsun, bir kupon kazandınız.")

            im2.execute("SELECT * From etkinlikler3 ")
            rows = im2.fetchall()
            for row in rows:
              Etkinlik_listesi = str (row)

              #print(Etkinlik_listesi)
              Etkinlik_listesi_veriler = Etkinlik_listesi.split(',')
              #print(Etkinlik_listesi_veriler [3])

              Etkinlik_bitis_tarihi_str = Etkinlik_listesi_veriler[3].strip().strip("'")
              try:
                  Etkinlik_bitis_tarihi_date = dt.datetime.strptime(Etkinlik_bitis_tarihi_str, "%d/%m/%Y").date()
              except ValueError:
                  # If date format is not as expected, skip this event
                  continue

              today_date = dt.date.today()
              if Etkinlik_bitis_tarihi_date < today_date:
                  # Skip past events
                  continue

              if (Etkinlik_listesi_veriler[4] == " 'Atletizm'" and my_veriler[5] == " '1'" ):
                btn_text = "Atletizm: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'Jimnastik'" and my_veriler[6] == " '1'" ):
                btn_text = "Jimnastik: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'MotorSporlari'" and my_veriler[7] == " '1'" ):
                btn_text = "MotorSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'TakimSporlari'" and my_veriler[8] == " '1'" ):
                btn_text = "TakimSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'RaketSporlari'" and my_veriler[9] == " '1'" ):
                btn_text = "RaketSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'DovusSporlari'" and my_veriler[10] == " '1'" ):
                btn_text = "DovusSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'SuSporlari'" and my_veriler[11] == " '1'" ):
                btn_text = "SuSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'HayvanliSporlar'" and my_veriler[12] == " '1'" ):
                btn_text = "HayvanliSporlar: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'ExtremSporlar'" and my_veriler[13] == " '1'" ):
                btn_text = "ExtremSporlar: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'KisSporlari'" and my_veriler[14] == " '1'" ):
                btn_text = "KisSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'TekerlekliSporlar'" and my_veriler[15] == " '1'" ):
                btn_text = "TekerlekliSporlar: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'HedefSporlari'" and my_veriler[16] == " '1'" ):
                btn_text = "HedefSporlari: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (Etkinlik_listesi_veriler[4] == " 'ESpor'" and my_veriler[17] == " '1')]" ):
                btn_text = "ESpor: " + Etkinlik_listesi_veriler[1].strip().strip("'")
                event_info = f"Etkinlik İsmi: {Etkinlik_listesi_veriler[1].strip()}\nTarih: {Etkinlik_listesi_veriler[2].strip()}\nBitiş Tarihi: {Etkinlik_listesi_veriler[3].strip()}\nKategori: {Etkinlik_listesi_veriler[4].strip()}\nSaat: {Etkinlik_listesi_veriler[5].strip()}\nBitiş Saati: {Etkinlik_listesi_veriler[6].strip()}\nŞehir: {Etkinlik_listesi_veriler[7].strip()}\nNot: {Etkinlik_listesi_veriler[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)
              
              
              
              





        else:
            result_label.config(text="Parola veya kullanıcı adı yanlış!")
    giris_button["command"] = login
    
    def etkinlik_olustur(): 
      etkinlik_olustur_pencere = Toplevel()
      etkinlik_olustur_pencere.geometry("1024x1024")
      etkinlik_olustur_pencere.title("Etkinlik Oluştur")
       
      oluştur_label = ttk.Label(etkinlik_olustur_pencere, text = "Etkinlik Oluştur", font=("Arial", 22, "bold"))
      oluştur_label.pack(pady=20)
    
      etkinlik_isim_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Adı:")
      etkinlik_isim_label.pack()
      etkinlik_isim_entry = ttk.Entry(etkinlik_olustur_pencere)
      etkinlik_isim_entry.pack()   

      Etkinlik_tarih_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Tarihi:")
      Etkinlik_tarih_label.pack()
      Etkinlik_tarih_entry = ttk.Entry(etkinlik_olustur_pencere)
      Etkinlik_tarih_entry.pack()   
      

      Etkinlik_bitiş_tarih_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Bitiş Tarihi:")
      Etkinlik_bitiş_tarih_label.pack()
      Etkinlik_bitiş_tarih_entry = ttk.Entry(etkinlik_olustur_pencere)
      Etkinlik_bitiş_tarih_entry.pack()   

      
      def on_select(event):
        print("Seçilen değer:", combo.get())


      Etkinlik_kategori_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Kategorisi:")
      Etkinlik_kategori_label.pack()

      options = ["Atletizm", "Jimnastik", "MotorSporlari", "TakimSporlari", "RaketSporlari", "DovusSporlari", "SuSporlari", "HayvanliSporlar", "ExtremSporlar", "KisSporlari", "TekerlekliSporlar", "HedefSporlari", "ESpor"]
      combo = ttk.Combobox(etkinlik_olustur_pencere, values=options)
      combo.bind("<<ComboboxSelected>>", on_select)
      combo.pack()

      
      def on_select1(event):
        print("Seçilen değer:", saatcombo.get())


      Etkinlik_saat_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Saati:")
      Etkinlik_saat_label.pack()

      options = ["00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45", "02:00", "02:15", "02:30", "02:45", 
           "03:00", "03:15", "03:30", "03:45", "04:00", "04:15", "04:30", "04:45", "05:00", "05:15", "05:30", "05:45", 
           "06:00", "06:15", "06:30", "06:45", "07:00", "07:15", "07:30", "07:45", "08:00", "08:15", "08:30", "08:45", 
           "09:00", "09:15", "09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", 
           "12:00", "12:15", "12:30", "12:45", "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30", "14:45", 
           "15:00", "15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45", "17:00", "17:15", "17:30", "17:45", 
           "18:00", "18:15", "18:30", "18:45", "19:00", "19:15", "19:30", "19:45", "20:00", "20:15", "20:30", "20:45", 
           "21:00", "21:15", "21:30", "21:45", "22:00", "22:15", "22:30", "22:45", "23:00", "23:15", "23:30", "23:45"]
      saatcombo = ttk.Combobox(etkinlik_olustur_pencere, values=options)
      saatcombo.bind("<<ComboboxSelected>>", on_select1)
      saatcombo.pack()

      


      def on_select2(event):
        print("Seçilen değer:", bitissaatcombo.get())


      Etkinlik_bitiş_saat_label = ttk.Label(etkinlik_olustur_pencere, text="Etkinliğin Bitiş Saati:")
      Etkinlik_bitiş_saat_label.pack()
      
      options = ["00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45", "02:00", "02:15", "02:30", "02:45", 
           "03:00", "03:15", "03:30", "03:45", "04:00", "04:15", "04:30", "04:45", "05:00", "05:15", "05:30", "05:45", 
           "06:00", "06:15", "06:30", "06:45", "07:00", "07:15", "07:30", "07:45", "08:00", "08:15", "08:30", "08:45", 
           "09:00", "09:15", "09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", 
           "12:00", "12:15", "12:30", "12:45", "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30", "14:45", 
           "15:00", "15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45", "17:00", "17:15", "17:30", "17:45", 
           "18:00", "18:15", "18:30", "18:45", "19:00", "19:15", "19:30", "19:45", "20:00", "20:15", "20:30", "20:45", 
           "21:00", "21:15", "21:30", "21:45", "22:00", "22:15", "22:30", "22:45", "23:00", "23:15", "23:30", "23:45"]
      bitissaatcombo = ttk.Combobox(etkinlik_olustur_pencere, values=options)
      bitissaatcombo.bind("<<ComboboxSelected>>", on_select2)
      bitissaatcombo.pack()

      def on_select3(event):
        print("Seçilen değer:", sehirler.get())


      Etkinlik_sehir_label = ttk.Label(etkinlik_olustur_pencere, text="Şehir:")
      Etkinlik_sehir_label.pack()

      options = ["Adana", "Adıyaman", "Afyonkarahisar", "Aksaray", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kastamonu", "Kayseri", "Kilis", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak"]
      sehirler = ttk.Combobox(etkinlik_olustur_pencere, values=options)
      sehirler.bind("<<ComboboxSelected>>", on_select3)
      sehirler.pack()

      Not_label = ttk.Label(etkinlik_olustur_pencere, text="Not:")
      Not_label.pack()
      Not_entry = ttk.Entry(etkinlik_olustur_pencere)
      Not_entry.pack()   
      
      
      etkinlik_olustur_button= ttk.Button(etkinlik_olustur_pencere, text="Etkinliği oluştur", command = etkinlik_olustur)
      etkinlik_olustur_button.pack() 

      etkinlik_label = ttk.Label(etkinlik_olustur_pencere)
      etkinlik_label.pack()
  
      def etkinlik_create():
          Etkinlik_name = etkinlik_isim_entry.get()
          Etkinlik_date = Etkinlik_tarih_entry.get()
          Etkinlik_end_date = Etkinlik_bitiş_tarih_entry.get()
          Etkinlik_category = combo.get()
          Etkinlik_time = saatcombo.get()
          Etkinlik_end_time = bitissaatcombo.get()
          Etkinlik_city = sehirler.get()
          Note = Not_entry.get()
          kull1= kullanici_entry.get()
          im2.execute("INSERT INTO etkinlikler3 (kullanici_adi, etkinlik_isim, Etkinlik_tarih, Etkinlik_bitiş_tarih, Etkinlik_kategori, Etkinlik_saat, Etkinlik_bitiş_saat, Etkinlik_sehir, Note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (kull1, Etkinlik_name, Etkinlik_date, Etkinlik_end_date, Etkinlik_category, Etkinlik_time, Etkinlik_end_time, Etkinlik_city, Note)) 
          tt.commit()

          im2.execute("SELECT * FROM etkinlikler3 WHERE etkinlik_isim = ?", (Etkinlik_name,))
          Etkinlik_durumu = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE kullanici_adi = ?", (kull1,))
          Etkinlik_durumu1 = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE Etkinlik_tarih = ?", (Etkinlik_date,))
          Etkinlik_durumu2 = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE Etkinlik_bitiş_tarih = ?", (Etkinlik_end_date,))
          Etkinlik_durumu3 = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE Etkinlik_saat = ?", (Etkinlik_time,))
          Etkinlik_durumu4 = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE Etkinlik_bitiş_saat = ?", (Etkinlik_end_time,))
          Etkinlik_durumu5 = im.fetchone()
          im2.execute("SELECT * FROM etkinlikler3 WHERE Etkinlik_sehir = ?", (Etkinlik_city,))
          Etkinlik_durumu6 = im.fetchone()


          nowgun1=dt.datetime.now().day # 
          noway1=dt.datetime.now().month # 
          nowyil1=dt.datetime.now().year #
          nowsaat1=dt.datetime.now().hour
          nowdakika1=dt.datetime.now().minute
          print(nowgun1)
          print(noway1)
          print(nowyil1)

          Etkinlik_date_control = Etkinlik_date.split('/')
          Etkinlik_date_control_day = int(Etkinlik_date_control[0])
          Etkinlik_date_control_ay = int(Etkinlik_date_control[1])
          Etkinlik_date_control_yil = int(Etkinlik_date_control[2])
          print(Etkinlik_date_control_day)
          print(Etkinlik_date_control_ay)
          print(Etkinlik_date_control_yil)


          Etkinlik_saat_control = Etkinlik_time.split(':')
          Etkinlik_saat_control_saat = int(Etkinlik_saat_control[0])
          Etkinlik_saat_control_dakika = int(Etkinlik_saat_control[1])

          Etkinlik_end_date_control = Etkinlik_end_date.split('/')
          Etkinlik_end_date_control_day = int(Etkinlik_end_date_control[0])
          Etkinlik_end_date_control_ay = int(Etkinlik_end_date_control[1])
          Etkinlik_end_date_control_yil = int(Etkinlik_end_date_control[2])
          print(Etkinlik_end_date_control_day)
          print(Etkinlik_end_date_control_ay)
          print(Etkinlik_end_date_control_yil)



          Etkinlik_end_saat_control = Etkinlik_end_time.split(':')
          Etkinlik_end_saat_control_saat = int(Etkinlik_end_saat_control[0])
          Etkinlik_end_saat_control_dakika = int(Etkinlik_end_saat_control[1])


          if not Etkinlik_name:
            etkinlik_label.config(text="Etkinlik ismi boş bırakılamaz.")
            return
      
          elif not Etkinlik_date:
            etkinlik_label.config(text="Etkinlik tarihi boş bırakılamaz.")
            return
           
          elif not Etkinlik_end_date:
            etkinlik_label.config(text="Etkinlik bitiş tarihi boş bırakılamaz.")
            return
          
          elif not Etkinlik_time:
            etkinlik_label.config(text="Etkinlik saati boş bırakılamaz.")
            return
          elif not Etkinlik_end_time:
            etkinlik_label.config(text="Etkinlik bitiş saati boş bırakılamaz.")
            return
          
          elif not Etkinlik_city:
            etkinlik_label.config(text="Etkinlik şehri boş bırakılamaz.")
            return
           
          elif Etkinlik_durumu and Etkinlik_durumu1 and Etkinlik_durumu2 and Etkinlik_durumu3 and Etkinlik_durumu4 and Etkinlik_durumu5 and Etkinlik_durumu6:
            etkinlik_label.config(text="Bu etkinlik zaten oluşturulmuş.")
            return

          elif Etkinlik_end_date_control_yil < Etkinlik_date_control_yil:
            etkinlik_label.config(text="Etkinlik bitiş ve başlangıç tarihlerini uygun seçiniz.")
            return

          elif Etkinlik_end_date_control_yil == Etkinlik_date_control_yil and Etkinlik_end_date_control_ay < Etkinlik_date_control_ay:
            etkinlik_label.config(text="Etkinlik tarihini lütfen uygun seçiniz.")
            return

          elif Etkinlik_end_date_control_yil == Etkinlik_date_control_yil and Etkinlik_end_date_control_ay == Etkinlik_date_control_ay and Etkinlik_end_date_control_day < Etkinlik_date_control_day:
            etkinlik_label.config(text="Etkinlik tarihini lütfen uygun seçiniz.")
            return

          elif Etkinlik_end_date_control_yil == Etkinlik_date_control_yil and Etkinlik_end_date_control_ay == Etkinlik_date_control_ay and Etkinlik_end_date_control_day == Etkinlik_date_control_day and Etkinlik_end_saat_control < Etkinlik_saat_control:
            etkinlik_label.config(text="Etkinlik tarihini lütfen uygun seçiniz.")
            return

          elif Etkinlik_end_date_control_yil == Etkinlik_date_control_yil and Etkinlik_end_date_control_ay == Etkinlik_date_control_ay and Etkinlik_end_date_control_day == Etkinlik_date_control_day and Etkinlik_end_saat_control == Etkinlik_saat_control and Etkinlik_end_saat_control_dakika < Etkinlik_saat_control_dakika:
            etkinlik_label.config(text="Etkinlik tarihini lütfen uygun seçiniz.")
            return

          elif Etkinlik_date_control_yil < nowyil1 or Etkinlik_date_control_yil > nowyil1 + 100:
            etkinlik_label.config(text="Etkinlik tarihi bugünden önce veya çok sonrasına olamaz.")
            return

          elif Etkinlik_date_control_yil == nowyil1 and Etkinlik_date_control_ay < noway1:
            etkinlik_label.config(text="Etkinlik tarihi bugünden önce olamaz.")
            return

          elif Etkinlik_date_control_yil == nowyil1 and Etkinlik_date_control_ay == noway1 and Etkinlik_date_control_day < nowgun1:
            etkinlik_label.config(text="Etkinlik tarihi bugünden önce olamaz.")
            return

          elif Etkinlik_date_control_yil == nowyil1 and Etkinlik_date_control_ay == noway1 and Etkinlik_date_control_day == nowgun1 and Etkinlik_saat_control_saat < nowsaat1:
            etkinlik_label.config(text="Etkinlik tarihi bugünden önce olamaz.")
            return

          elif Etkinlik_date_control_yil == nowyil1 and Etkinlik_date_control_ay == noway1 and Etkinlik_date_control_day == nowgun1 and Etkinlik_saat_control_saat == nowsaat1 and Etkinlik_saat_control_dakika < nowdakika1:
            etkinlik_label.config(text="Etkinlik tarihi bugünden önce olamaz.")
            return


          else:
            
            im2.execute("INSERT INTO etkinlikler3 (kullanici_adi, etkinlik_isim, Etkinlik_tarih, Etkinlik_bitiş_tarih, Etkinlik_kategori, Etkinlik_saat, Etkinlik_bitiş_saat, Etkinlik_sehir, Note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (kull1, Etkinlik_name, Etkinlik_date, Etkinlik_end_date, Etkinlik_category, Etkinlik_time, Etkinlik_end_time, Etkinlik_city, Note)) 
            tt.commit()
            etkinlik_label.config(text="Etkinliğiniz başarıyla kaydedildi.")
      etkinlik_olustur_button ["command"] = etkinlik_create
      etkinlik_olustur_button.pack()








def uye_girisi_ac():

     
    uyegirisi_pencere = Toplevel()
    baslik = Label(uyegirisi_pencere, text="Üye olma")
    baslik.pack()
    #anapencere.withdraw()
    uyegirisi_pencere.geometry("1024x1024")

    # Üye olma kısmı
    uye_ol_label = ttk.Label(uyegirisi_pencere, text="Üye Ol", font=("Arial", 16, "bold"))
    uye_ol_label.pack(pady=10)


    CheckVar1 = IntVar()
    CheckVar2 = IntVar()
    CheckVar3 = IntVar()
    CheckVar4 = IntVar()
    CheckVar5 = IntVar()
    CheckVar6 = IntVar()
    CheckVar7 = IntVar()
    CheckVar8 = IntVar()
    CheckVar9 = IntVar()
    CheckVar10 = IntVar()
    CheckVar11 = IntVar()
    CheckVar12 = IntVar()
    CheckVar13 = IntVar()
    
    Label11= Label(uyegirisi_pencere, text="İlgilendiğiniz spor alanları:")
    Atletizm = Checkbutton(uyegirisi_pencere, text = "Atletizm", variable = CheckVar1, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20, )
    Jimnastik = Checkbutton(uyegirisi_pencere, text = "Jimnastik", variable = CheckVar2, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    MotorSporlari = Checkbutton(uyegirisi_pencere, text = "Motor Sporları", variable = CheckVar3, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    TakimSporlari = Checkbutton(uyegirisi_pencere, text = "Takım Sporları", variable = CheckVar4, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    RaketSporlari = Checkbutton(uyegirisi_pencere, text = "Raket Sporları", variable = CheckVar5, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    DovusSporlari = Checkbutton(uyegirisi_pencere, text = "Dövüş Sporları", variable = CheckVar6, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    SuSporlari = Checkbutton(uyegirisi_pencere, text = "Su Sporları", variable = CheckVar7, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    HayvanliSporlar = Checkbutton(uyegirisi_pencere, text = "Hayvanlı Sporlar", variable = CheckVar8, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    ExtremSporlar = Checkbutton(uyegirisi_pencere, text = "Extrem Sporlar", variable = CheckVar9, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    KisSporlari = Checkbutton(uyegirisi_pencere, text = "Kış Sporları", variable = CheckVar10, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    TekerlekliSpoarlar= Checkbutton(uyegirisi_pencere, text = "Tekerlekli Sporlar", variable = CheckVar11, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    HedefSporlari = Checkbutton(uyegirisi_pencere, text = "Hedef Sporları", variable = CheckVar12, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    ESpor = Checkbutton(uyegirisi_pencere, text = "E-Spor", variable = CheckVar13, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    Label11.pack()
    Atletizm.pack()
    Jimnastik.pack()
    MotorSporlari.pack()
    TakimSporlari.pack()
    RaketSporlari.pack()
    DovusSporlari.pack()
    SuSporlari.pack()
    HayvanliSporlar.pack()
    ExtremSporlar.pack()
    KisSporlari.pack()
    TekerlekliSpoarlar.pack()
    HedefSporlari.pack()
    ESpor.pack()


    Atletizm = str(Atletizm)
    Jimnastik = str(Jimnastik)
    MotorSporlari = str(MotorSporlari)
    TakimSporlari = str(TakimSporlari)
    RaketSporlari = str(RaketSporlari)
    DovusSporlari = str(DovusSporlari)
    SuSporlari = str(SuSporlari)
    HayvanliSporlar = str(HayvanliSporlar)
    ExtremSporlar = str(ExtremSporlar)
    KisSporlari = str(KisSporlari)
    TekerlekliSpoarlar = str(TekerlekliSpoarlar)
    HedefSporlari = str(HedefSporlari)
    ESpor = str(ESpor)

    # Kullanıcı adı etiketi ve giriş alanı
    kullanici_label2 = ttk.Label(uyegirisi_pencere, text="Kullanıcı Adı:")
    kullanici_label2.pack()
    kullanici_giris = ttk.Entry(uyegirisi_pencere)
    kullanici_giris.pack()

    # Şifre etiketi ve giriş alanı
    sifre_label = ttk.Label(uyegirisi_pencere, text="Şifre:")
    sifre_label.pack()
    sifre_giris = ttk.Entry(uyegirisi_pencere, show="*")
    sifre_giris.pack()

    # Şifre tekrar etiketi ve giriş alanı
    sifre2_label = ttk.Label(uyegirisi_pencere, text="Şifre (Tekrar):")
    sifre2_label.pack()
    sifre2_giris = ttk.Entry(uyegirisi_pencere, show="*")
    sifre2_giris.pack()

    # Gmail etiketi ve giriş alanı
    gmail_label = ttk.Label(uyegirisi_pencere, text="Gmail:")
    gmail_label.pack()
    gmail_entry = ttk.Entry(uyegirisi_pencere)
    gmail_entry.pack()
   
    # Ad Soyad etiketi ve giriş alanı
    adsoyad_label = ttk.Label(uyegirisi_pencere, text="Ad Soyad:")
    adsoyad_label.pack()
    adsoyad_entry = ttk.Entry(uyegirisi_pencere)
    adsoyad_entry.pack()

    # Doğum Tarihi etiketi ve giriş alanı
    dogum_tarihi_label = ttk.Label(uyegirisi_pencere, text="Doğum Tarihi:")
    dogum_tarihi_label.pack()
    dogum_tarihi_entry = ttk.Entry(uyegirisi_pencere)
    #dogum_tarihi_entry.pack()
    #now=dt.datetime.now()
    nowgun=dt.datetime.now().day # 
    noway=dt.datetime.now().month # 
    nowyil=dt.datetime.now().year # 
    
    
    # Add Calendar
    cal = Calendar(uyegirisi_pencere, selectmode = 'day',
                year = (nowyil-15), month = noway,
                day = nowgun, dogumyili = noway and nowgun)
 
    cal.pack(pady = 0)




    date = Label(uyegirisi_pencere, text = "")
    date.pack(pady = 0)
    # Üye ol düğmesi
    uyeol_button = ttk.Button(uyegirisi_pencere, text="Üye Ol")
    uyeol_button.pack(pady=0)

    result_label1 = ttk.Label(uyegirisi_pencere, text="")
    result_label1.pack(pady=0)

    

    def register():
    


        kullanici_adi = kullanici_giris.get()
        sifre = sifre_giris.get()
        sifre_tekrar = sifre2_giris.get()
        gmail = gmail_entry.get()
        adsoyad = adsoyad_entry.get()
        dogum_tarihi = cal.get_date()
    
        dogum_tarihi=dt.datetime.strptime(dogum_tarihi,"%m/%d/%y")
        simdi=dt.datetime.now()
        fark=simdi-dogum_tarihi 
        yil=fark.days//365
        #if yil < 0:
        #yil = (yil*(-1))
        epostach=str(gmail)
        sayac=0
        count=0
        while sayac < (len(epostach)-1):
           sayac += 1
           if epostach[sayac]=="@":
               count+= 1

        im.execute("SELECT * FROM kullanicilar2 WHERE kullanici_adi = ?", (kullanici_adi,))
        data = im.fetchone()
        im.execute("SELECT * FROM kullanicilar2 WHERE gmail = ?", (gmail,))
        epostakontrol = im.fetchone()
        # Kullanıcı adının boş olup olmadığını kontrol ediyoruz
        if not kullanici_adi:
            result_label1.config(text="Kullanıcı adı boş bırakılamaz.")
            return
        
            # Şifrenin boş olup olmadığını kontrol ediyoruz
        elif not sifre:
            result_label1.config(text="Şifre boş bırakılamaz.")
            return
            # Şifrelerin eşleşip eşleşmediğini kontrol ediyoruz
        elif sifre != sifre_tekrar:
            result_label1.config(text="Şifreler eşleşmiyor.")
            return
            # Kullanıcı adının veritabanında kullanılıp kullanılmadığını kontrol ediyoruz
        elif data:
            result_label1.config(text="Bu kullanıcı adı zaten kullanılıyor.")
        elif epostakontrol:
            result_label1.config(text="Bu e-posta zaten kullanılıyor.")
        elif count !=1:
            result_label1.config(text="lütfen geçerli bir e-posta adresi giriniz.")
        elif (yil < 15 or yil > 123):
            result_label1.config(text=yil)
            #result_label1.config(text="Bu uygulamanın kullanımı için belirtilen yaş aralığına uygun değilsiniz.")
        else:
            # Yeni kullanıcıyı veritabanına ekliyoruz
            im.execute("INSERT INTO kullanicilar2 (kullanici_adi, parola, gmail, adsoyad, dogum_tarihi, Atletizm, Jimnastik, MotorSporlari, TakimSporlari, RaketSporlari, DovusSporlari, SuSporlari, HayvanliSporlar, ExtremSporlar, KisSporlari, TekerlekliSpoarlar, HedefSporlari, ESpor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )",
                   (kullanici_adi, sifre, gmail, adsoyad, dogum_tarihi, CheckVar1.get(), CheckVar2.get(), CheckVar3.get(), CheckVar4.get(), CheckVar5.get(), CheckVar6.get(), CheckVar7.get(), CheckVar8.get(), CheckVar9.get(), CheckVar10.get(), CheckVar11.get(), CheckVar12.get(), CheckVar13.get())) 
            vt.commit()
            result_label1.config(text="Üyelik başarıyla oluşturuldu.")
            uyeol_button["command"] = register


        im.execute("SELECT * FROM kullanicilar2 WHERE kullanici_adi = ?", (kullanici_adi,))
        data = im.fetchone()
        im.execute("SELECT * FROM kullanicilar2 WHERE gmail = ?", (gmail,))
        epostakontrol = im.fetchone()
        # Kullanıcı adının boş olup olmadığını kontrol ediyoruz
        if not kullanici_adi:
            result_label1.config(text="Kullanıcı adı boş bırakılamaz.")
            return
        
            # Şifrenin boş olup olmadığını kontrol ediyoruz
        elif not sifre:
            result_label1.config(text="Şifre boş bırakılamaz.")
            return
            # Şifrelerin eşleşip eşleşmediğini kontrol ediyoruz
        elif sifre != sifre_tekrar:
            result_label1.config(text="Şifreler eşleşmiyor.")
            return
            # Kullanıcı adının veritabanında kullanılıp kullanılmadığını kontrol ediyoruz
        elif data:
            result_label1.config(text="Bu kullanıcı adı zaten kullanılıyor.")
        elif epostakontrol:
            result_label1.config(text="Bu e-posta zaten kullanılıyor.")
        elif count !=1:
            result_label1.config(text="lütfen geçerli bir e-posta adresi giriniz.")
        elif (yil < 15 or yil > 123):
            result_label1.config(text=yil)
            #result_label1.config(text="Bu uygulamanın kullanımı için belirtilen yaş aralığına uygun değilsiniz.")
        else:
            # Yeni kullanıcıyı veritabanına ekliyoruz
            im.execute("INSERT INTO kullanicilar2 (kullanici_adi, parola, gmail, adsoyad, dogum_tarihi, Atletizm, Jimnastik, MotorSporlari, TakimSporlari, RaketSporlari, DovusSporlari, SuSporlari, HayvanliSporlar, ExtremSporlar, KisSporlari, TekerlekliSpoarlar, HedefSporlari, ESpor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )",
                   (kullanici_adi, sifre, gmail, adsoyad, dogum_tarihi, CheckVar1.get(), CheckVar2.get(), CheckVar3.get(), CheckVar4.get(), CheckVar5.get(), CheckVar6.get(), CheckVar7.get(), CheckVar8.get(), CheckVar9.get(), CheckVar10.get(), CheckVar11.get(), CheckVar12.get(), CheckVar13.get())) 
            vt.commit()
            result_label1.config(text="Üyelik başarıyla oluşturuldu.")
    uyeol_button["command"] = register
 




# Set screensize as fullscreen and not resizable
anapencere.geometry("1024x1024")
anapencere.resizable(False, False)


# Add Connect, Share, Inspire! slogan next to the button frame
imgconnect = Image.open("C:/Users/Admin/Downloads/sporting-goods-volleyball-coach-badminton-removebg-preview (1).png")
img2 = ImageTk.PhotoImage(imgconnect)
imgconnect = imgconnect.resize((550, 500))
img2 = ImageTk.PhotoImage(imgconnect)


label = Label(anapencere, image=img2, bg="#FFFDD0", borderwidth=0)
label.place(x=50, y=175)



# Add Sign Up and Sign In buttons with improved style
style = ttk.Style()
style.configure('TButton', relief=RAISED, font=('Arial', 20), padding=10)
style.map('TButton', foreground=[('active', 'white')], background=[('active', 'light blue')])

# Create a frame for buttons
button_frame = Frame(anapencere, bg='moccasin', bd=2, relief = RAISED)
button_frame.place(x=1000, y=150, width=400, height=550, anchor='ne')

signup_button = ttk.Button(button_frame, text='Sign Up', style='TButton', command=uye_girisi_ac)
signup_button.place(x=117, y=250)

signin_button = ttk.Button(button_frame, text='Sign In', style='TButton', command=uye_kaydi_ac)
signin_button.place(x=117, y=350)

# Add SocialCircle label at the top-left corner
imgSC = Image.open("C:/Users/Admin/Desktop/Python/SC.png")
img1 = ImageTk.PhotoImage(imgSC)
imgSC = imgSC.resize((150,150))
img1 = ImageTk.PhotoImage(imgSC)


label = Label(anapencere, image=img1, bg="#FFFFFF", borderwidth=0)

label.place(x=735, y=180)




# Veritabanı üzerinde işlem yapabilmek için bir imleç oluşturuyoruz
im = vt.cursor()


# İmlecin execute() metoduyla kullanicilar adında bir tablo oluşturuyoruz
# Bu tabloda kullanici_adi, parola, gmail, adsoyad ve dogum_tarihi ilgilendiği spor dalları sütunları bulunmaktadır
im.execute("""CREATE TABLE IF NOT EXISTS kullanicilar2
    (kullanici_adi TEXT, parola TEXT, gmail TEXT, adsoyad TEXT, dogum_tarihi TEXT, Atletizm TEXT ,Jimnastik TEXT ,MotorSporlari TEXT ,TakimSporlari TEXT ,RaketSporlari TEXT ,DovusSporlari TEXT ,
SuSporlari TEXT ,HayvanliSporlar TEXT ,ExtremSporlar TEXT ,KisSporlari TEXT ,TekerlekliSpoarlar TEXT ,HedefSporlari TEXT ,ESpor TEXT)""")




# Yaptığımız değişiklikleri kaydediyoruz
vt.commit()

im2 = tt.cursor()

im2.execute("""CREATE TABLE IF NOT EXISTS etkinlikler3
    (kullanici_adi TEXT, etkinlik_isim TEXT, Etkinlik_tarih TEXT, Etkinlik_bitiş_tarih TEXT, Etkinlik_kategori TEXT, Etkinlik_saat TEXT, Etkinlik_bitiş_saat TEXT, Etkinlik_sehir TEXT, Note TEXT)""")


tt.commit()

anapencere.mainloop()