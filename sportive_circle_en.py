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
main_window = Toplevel()

ico = Image.open('C:/Users/Admin/Downloads/SC.ico')
photo = ImageTk.PhotoImage(ico)
main_window.wm_iconphoto(False, photo)

main_window.title("SocialCircle")
main_window.config(bg="#f0f2f5")  # Light background for modern look
users_db = sqlite3.connect('C:/Users/Admin/Python/users.sqlite')  # Edit the database file path
events_db = sqlite3.connect('C:/Users/Admin/Python/events.sqlite')  # Edit the database file path

def open_sign_in_window():

    auth_window = Toplevel()
    header_label = Label(auth_window, text="Member Login")
    header_label.pack()
    #main_window.withdraw()
    auth_window.geometry("1024x1024")
    # Login section
    login_title_label = ttk.Label(auth_window, text="Login", font=("Segoe UI", 18, "bold"), foreground="#333")
    login_title_label.pack(pady=20)
        # Username label and input field
    username_label = ttk.Label(auth_window, text="Username:", font=("Segoe UI", 12))
    username_label.pack(pady=(10, 0))
    username_entry = ttk.Entry(auth_window, font=("Segoe UI", 12))
    username_entry.pack(pady=(0, 10), ipadx=5, ipady=5)
    # Password label and input field
    password_label = ttk.Label(auth_window, text="Password:", font=("Segoe UI", 12))
    password_label.pack(pady=(10, 0))
    password_entry = ttk.Entry(auth_window, show="*", font=("Segoe UI", 12))
    password_entry.pack(pady=(0, 10), ipadx=5, ipady=5)
    
    # Result label
    result_label = ttk.Label(auth_window, text="", font=("Segoe UI", 10), foreground="red")
    result_label.pack(pady=12)
    # Login button
    login_button = ttk.Button(auth_window, text="Login", style="Accent.TButton")
    
    login_button.pack(pady=10, ipadx=10, ipady=5)
    #login_button(x=500,y=600)


    #tried all the images, none of them show up, just a white background
    imgcross = Image.open("C:/Users/Admin/Desktop/Python/takım sporları.png")
    img50 = ImageTk.PhotoImage(imgSC)
    imgcross = imgcross.resize((150,150))
    img50 = ImageTk.PhotoImage(imgSC)


    label40 = Label(auth_window, image=img50, bg="#FFFFFF", borderwidth=0)

    label40.place(x=735, y=180)


   


    def login():
        
        # Get the username and password from the user
        username = username_entry.get()
        password = password_entry.get()
        
        # Check the username and password in the database 
        users_cursor.execute("""SELECT * FROM users WHERE
        username = ? AND password = ? """,
                (username, password,))
        data = users_cursor.fetchall()
        # Check the results coming from the database
        
        if data:
            result_label.config(text="Welcome to the app, " + username + " :D")
            mainpage = Tk()
            mainpage.title("Main Page")
            event_button = ttk.Button(mainpage, text="add event", command = open_create_event_window)
            event_button.pack(pady=0)
            event_button = ttk.Label(mainpage, text = "")
            event_button.pack()
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
                    "Athletics", "Gymnastics", "MotorSports", "TeamSports", 
                    "RacketSports", "CombatSports", "WaterSports", "AnimalSports",
                    "ExtremeSports", "WinterSports", "WheelSports", "TargetSports", "ESports"
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
                    events_cursor.execute("SELECT * FROM events")
                    rows = events_cursor.fetchall()
                    for row in rows:
                        event_row_str = str(row)
                        event_fields = event_row_str.split(',')

                        event_end_date_str = event_fields[3].strip().strip("'")
                        try:
                            event_end_date_obj = dt.datetime.strptime(event_end_date_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue

                        today_date = dt.date.today()
                        if event_end_date_obj < today_date:
                            continue

                        category = event_fields[4].strip().strip("'")
                        city = event_fields[7].strip().strip("'")

                        # Apply category filter
                        if selected_category and category != selected_category:
                            continue
                            
                        # Apply city filter
                        if selected_city and city != selected_city:
                            continue

                        # Create button for the event
                        stripped_name = event_fields[1].strip().strip('"')
                        btn_text = f"{category}: {stripped_name}"
                        event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
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
                    events_cursor.execute("SELECT * FROM events")
                    rows = events_cursor.fetchall()
                    for row in rows:
                        event_row_str = str(row)
                        event_fields = event_row_str.split(',')
                        
                        event_end_date_str = event_fields[3].strip().strip("'")
                        try:
                            event_end_date_obj = dt.datetime.strptime(event_end_date_str, "%d/%m/%Y").date()
                        except ValueError:
                            continue
                        
                        today_date = dt.date.today()
                        if event_end_date_obj < today_date:
                            continue
                        
                        category = event_fields[4].strip().strip("'")
                        
                        # Create button for the event
                        stripped_name = event_fields[1].strip().strip('"')
                        btn_text = f"{category}: {stripped_name}"
                        event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                        btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                        btn.pack(pady=2)

            def show_event_details(event_info):
                detail_window = Toplevel(mainpage)
                detail_window.title("Event Details")
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
            users_cursor.execute("""SELECT * FROM users WHERE username = ?;
             """,
                   (username, ))
            result_label.config(text = data)
            user_data_str = str(data)
            user_fields = user_data_str.split(',')
            #print(user_fields[7])
            #print(user_fields[8])
            #print(user_fields[9])
            data = users_cursor.fetchall()
            birth_date_field = user_fields[4]
            birthday_parts = birth_date_field.split()
            birthday_date_parts = birthday_parts[0].split("-")
            birthday_month = birthday_date_parts[1]
            birthday_day = birthday_date_parts[2]  
            today1 = date.today()
            today2 = str(today1)
            today_parts = today2.split("-")
            print(today_parts[1],today_parts[2])
            print (today1) 
            current_month = today_parts[1]
            current_day = today_parts[2]
            if (user_fields[5] == " '1'" ):
              result_label2.config(text = "You're interested in Athletics")
              print ("You're interested in Athletics")
              print(user_fields[5])
              #imgatletizm = Image.open("C:/Users/Admin/Desktop/Python/atletizim.png")
              #img3 = ImageTk.PhotoImage(imgatletizm)

              #label = Label(mainpage, image=img3)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            if (user_fields[6] == " '1'" ):
              result_label3.config(text = "You're interested in Gymnastics" ,font=("Helvictia", 24 , "bold" ))
              print ("You're interested in Gymnastics")
              #imgjimnastik = Image.open("C:/Users/Admin/Desktop/Python/jimnastik.png")
              #img4 = ImageTk.PhotoImage(imgjimnastik)

              #label = Label(mainpage, image=img4)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=200, y=175)

            if (user_fields[7] == " '1'" ):
              result_label4.config(text = "You're interested in Motor Sports" ,font=("Helvictia", 24 , "bold" ))
              print ("You're interested in Motor Sports")
              

              #imgmotor = Image.open("C:/Users/Admin/Desktop/Python/images.png")
              #img5 = ImageTk.PhotoImage(imgmotor)

              #label510 = Label(mainpage, image=img5)
              #label510.pack(side='top left', fill=Y, expand=True)
              #label510.place(x=50, y=175)
              #result_label4.config(img5, text = "You're interested in Motor Sports")

             # label510 = Label(mainpage, image=img5, bg="#FFFFFF", borderwidth=0)


            if (user_fields[8] == " '1'" ):
              result_label5.config(text = "You're interested in Team Sports")
              #messagebox.showinfo("Your interests", "You're interested in Team Sports") 
              print ("You're interested in Team Sports")
              
              #imgtakim = Image.open("C:/Users/Admin/Desktop/Python/takım sporları.png")
              #img6 = ImageTk.PhotoImage(imgtakim)

              #label = Label(mainpage, image=img6)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)              
            if (user_fields[9] == " '1'" ):
              result_label6.config(text = "You're interested in Racket Sports")
              print (user_fields[9])

              #imgraket = Image.open("C:/Users/Admin/Desktop/Python/raket.png")
              #img7 = ImageTk.PhotoImage(imgraket)

              #label = Label(mainpage, image=img7)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            if (user_fields[10] == " '1'" ):
              result_label7.config(text = "You're interested in Combat Sports")
              print (user_fields[10])
              
              #imgdovus = Image.open("C:/Users/Admin/Desktop/Python/dövüş sporları.png")
              #img8 = ImageTk.PhotoImage(imgdovus)

              #label = Label(mainpage, image=img8)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)
            
            if (user_fields[11] == " '1'" ):
              result_label8.config(text = "You're interested in Water Sports")
              #messagebox.showinfo("Your interests", "You're interested in Water Sports") 
              print (user_fields[11])

                    # Add SocialCircle label at the top-left corner
                #imgSC = Image.open("C:/Users/Admin/Desktop/Python/SC.png")
            #img1 = ImageTk.PhotoImage(imgSC)
                  #imgSC = imgSC.resize((150,150))
                #img1 = ImageTk.PhotoImage(imgSC)


                #label = Label(main_window, image=img1, bg="#FFFFFF", borderwidth=0)

                #label.place(x=735, y=180)


              #imgsu = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")      
              #img9 = ImageTk.PhotoImage(imgsu)

              #label = Label(mainpage, image=img9)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=500, y=500)

            if (user_fields[12] == " '1'" ):
              result_label9.config(text = "You're interested in Animal Sports")
              print (user_fields[12])

              #imghayvan = Image.open("C:/Users/Admin/Desktop/Python/istockphoto-840182132-170667a.png")
              #img10 = ImageTk.PhotoImage(imghayvan)
              #imghayvan = imghayvan.resize((150,150))

              #label = Label(mainpage, image=img10)
              #label.pack(side='middle', fill=Y, expand=True)
              #label.place(x=500, y=500)

            if (user_fields[13] == " '1'" ):
              result_label10.config(text = "You're interested in Extreme Sports")
              print (user_fields[13])

              #imgextrem = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img11 = ImageTk.PhotoImage(imgextrem)

              #label = Label(mainpage, image=img11)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (user_fields[14] == " '1'" ):
              result_label11.config(text = "You're interested in Winter Sports")
              print (user_fields[14])

              #imgkis = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img12 = ImageTk.PhotoImage(imgkis)

              #label = Label(mainpage, image=img12)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (user_fields[15] == " '1'" ):
              result_label12.config(text = "You're interested in Wheel Sports")
              print (user_fields[15])

              #imgtekerlek = Image.open("C:/Users/Admin/Desktop/Python/Connect SHare Inspire.png")
              #img13 = ImageTk.PhotoImage(imgtekerlek)

              #label = Label(mainpage, image=img13)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (user_fields[16] == " '1'" ):
              result_label13.config(text = "You're interested in Target Sports")
              print (user_fields[16])

              #imghedef = Image.open("C:/Users/Admin/Desktop/Python/hedef tahtası.png")
              #img14 = ImageTk.PhotoImage(imghedef)

              #label = Label(mainpage, image=img14)
              #label.pack(side='top left', fill=Y, expand=True)
              #label.place(x=50, y=175)

            if (user_fields[17] == " '1')]" ):
              result_label14.config(text = "You're interested in E-Sports")
              print (user_fields[17])

              #imgespor = Image.open("C:/Users/Admin/Desktop/Python/e spor.png")
              #img15 = ImageTk.PhotoImage(imgespor)

              #label = Label(mainpage, image=img15)
              #label.pack(side='top left', fill=Y, expand=True)
             # label.place(x=50, y=175)
            
            if (user_fields[5] == " '0'" and user_fields[6] == " '0'" and  user_fields[7] == " '0'" and  user_fields[8] == " '0'" and  user_fields[9] == " '0'" and  user_fields[10] == " '0'" and  user_fields[11] == " '0'" and  user_fields[12] == " '0'" and  user_fields[13] == " '0'" and  user_fields[14] == " '0'" and  user_fields[15] == " '0'" and  user_fields[16] == " '0'" and  user_fields[17] == " '0')]"):
              result_label15.config(mainpage,text= "You're not interested in any sport")

              messagebox.showinfo("Your interests", "You're not interested in any sport")
            if (birthday_month == current_month and birthday_day == current_day):
              messagebox.showinfo("Happy 'escaped from your mom' anniversary, you won a coupon.")

            events_cursor.execute("SELECT * From events ")
            rows = events_cursor.fetchall()
            for row in rows:
              event_row_str = str (row)

              #print(event_row_str)
              event_fields = event_row_str.split(',')
              #print(event_fields [3])

              event_end_date_str = event_fields[3].strip().strip("'")
              try:
                  event_end_date_obj = dt.datetime.strptime(event_end_date_str, "%d/%m/%Y").date()
              except ValueError:
                  # If date format is not as expected, skip this event
                  continue

              today_date = dt.date.today()
              if event_end_date_obj < today_date:
                  # Skip past events
                  continue

              if (event_fields[4] == " 'Athletics'" and user_fields[5] == " '1'" ):
                btn_text = "Athletics: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'Gymnastics'" and user_fields[6] == " '1'" ):
                btn_text = "Gymnastics: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'MotorSports'" and user_fields[7] == " '1'" ):
                btn_text = "MotorSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'TeamSports'" and user_fields[8] == " '1'" ):
                btn_text = "TeamSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'RacketSports'" and user_fields[9] == " '1'" ):
                btn_text = "RacketSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'CombatSports'" and user_fields[10] == " '1'" ):
                btn_text = "CombatSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'WaterSports'" and user_fields[11] == " '1'" ):
                btn_text = "WaterSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'AnimalSports'" and user_fields[12] == " '1'" ):
                btn_text = "AnimalSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'ExtremeSports'" and user_fields[13] == " '1'" ):
                btn_text = "ExtremeSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'WinterSports'" and user_fields[14] == " '1'" ):
                btn_text = "WinterSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'WheelSports'" and user_fields[15] == " '1'" ):
                btn_text = "WheelSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'TargetSports'" and user_fields[16] == " '1'" ):
                btn_text = "TargetSports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)

              if (event_fields[4] == " 'ESports'" and user_fields[17] == " '1')]" ):
                btn_text = "ESports: " + event_fields[1].strip().strip("'")
                event_info = f"Event Name: {event_fields[1].strip()}\nDate: {event_fields[2].strip()}\nEnd Date: {event_fields[3].strip()}\nCategory: {event_fields[4].strip()}\nTime: {event_fields[5].strip()}\nEnd Time: {event_fields[6].strip()}\nCity: {event_fields[7].strip()}\nNote: {event_fields[8].strip()}"
                btn = Button(scrollable_frame, text=btn_text, width=50, command=lambda info=event_info: show_event_details(info))
                btn.pack(pady=2)
              
              
              
              





        else:
            result_label.config(text="Wrong password or username!")
    login_button["command"] = login
    
    def open_create_event_window(): 
      create_event_win = Toplevel()
      create_event_win.geometry("1024x1024")
      create_event_win.title("Create Event")
       
      create_title_label = ttk.Label(create_event_win, text = "Create Event", font=("Arial", 22, "bold"))
      create_title_label.pack(pady=20)
    
      event_name_label = ttk.Label(create_event_win, text="Event Name:")
      event_name_label.pack()
      event_name_entry = ttk.Entry(create_event_win)
      event_name_entry.pack()   

      event_date_label = ttk.Label(create_event_win, text="Event Date:")
      event_date_label.pack()
      event_date_entry = ttk.Entry(create_event_win)
      event_date_entry.pack()   
      

      event_end_date_label = ttk.Label(create_event_win, text="Event End Date:")
      event_end_date_label.pack()
      event_end_date_entry = ttk.Entry(create_event_win)
      event_end_date_entry.pack()   

      
      def on_select(event):
        print("Selected value:", combo.get())


      event_category_label = ttk.Label(create_event_win, text="Event Category:")
      event_category_label.pack()

      options = ["Athletics", "Gymnastics", "MotorSports", "TeamSports", "RacketSports", "CombatSports", "WaterSports", "AnimalSports", "ExtremeSports", "WinterSports", "WheelSports", "TargetSports", "ESports"]
      combo = ttk.Combobox(create_event_win, values=options)
      combo.bind("<<ComboboxSelected>>", on_select)
      combo.pack()

      
      def on_select1(event):
        print("Selected value:", time_combo.get())


      event_time_label = ttk.Label(create_event_win, text="Event Time:")
      event_time_label.pack()

      options = ["00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45", "02:00", "02:15", "02:30", "02:45", 
           "03:00", "03:15", "03:30", "03:45", "04:00", "04:15", "04:30", "04:45", "05:00", "05:15", "05:30", "05:45", 
           "06:00", "06:15", "06:30", "06:45", "07:00", "07:15", "07:30", "07:45", "08:00", "08:15", "08:30", "08:45", 
           "09:00", "09:15", "09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", 
           "12:00", "12:15", "12:30", "12:45", "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30", "14:45", 
           "15:00", "15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45", "17:00", "17:15", "17:30", "17:45", 
           "18:00", "18:15", "18:30", "18:45", "19:00", "19:15", "19:30", "19:45", "20:00", "20:15", "20:30", "20:45", 
           "21:00", "21:15", "21:30", "21:45", "22:00", "22:15", "22:30", "22:45", "23:00", "23:15", "23:30", "23:45"]
      time_combo = ttk.Combobox(create_event_win, values=options)
      time_combo.bind("<<ComboboxSelected>>", on_select1)
      time_combo.pack()

      


      def on_select2(event):
        print("Selected value:", end_time_combo.get())


      event_end_time_label = ttk.Label(create_event_win, text="Event End Time:")
      event_end_time_label.pack()
      
      options = ["00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45", "02:00", "02:15", "02:30", "02:45", 
           "03:00", "03:15", "03:30", "03:45", "04:00", "04:15", "04:30", "04:45", "05:00", "05:15", "05:30", "05:45", 
           "06:00", "06:15", "06:30", "06:45", "07:00", "07:15", "07:30", "07:45", "08:00", "08:15", "08:30", "08:45", 
           "09:00", "09:15", "09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "11:30", "11:45", 
           "12:00", "12:15", "12:30", "12:45", "13:00", "13:15", "13:30", "13:45", "14:00", "14:15", "14:30", "14:45", 
           "15:00", "15:15", "15:30", "15:45", "16:00", "16:15", "16:30", "16:45", "17:00", "17:15", "17:30", "17:45", 
           "18:00", "18:15", "18:30", "18:45", "19:00", "19:15", "19:30", "19:45", "20:00", "20:15", "20:30", "20:45", 
           "21:00", "21:15", "21:30", "21:45", "22:00", "22:15", "22:30", "22:45", "23:00", "23:15", "23:30", "23:45"]
      end_time_combo = ttk.Combobox(create_event_win, values=options)
      end_time_combo.bind("<<ComboboxSelected>>", on_select2)
      end_time_combo.pack()

      def on_select3(event):
        print("Selected value:", event_city_combo.get())


      event_city_label = ttk.Label(create_event_win, text="City:")
      event_city_label.pack()

      options = ["Adana", "Adıyaman", "Afyonkarahisar", "Aksaray", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kastamonu", "Kayseri", "Kilis", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak"]
      event_city_combo = ttk.Combobox(create_event_win, values=options)
      event_city_combo.bind("<<ComboboxSelected>>", on_select3)
      event_city_combo.pack()

      note_label = ttk.Label(create_event_win, text="note:")
      note_label.pack()
      note_entry = ttk.Entry(create_event_win)
      note_entry.pack()   
      
      
      create_event_button= ttk.Button(create_event_win, text="Create event", command = open_create_event_window)
      create_event_button.pack() 

      event_status_label = ttk.Label(create_event_win)
      event_status_label.pack()
  
      def save_event():
          event_name = event_name_entry.get()
          event_date = event_date_entry.get()
          event_end_date = event_end_date_entry.get()
          event_category = combo.get()
          event_time = time_combo.get()
          event_end_time = end_time_combo.get()
          event_city = event_city_combo.get()
          note = note_entry.get()
          creator_username= username_entry.get()
          events_cursor.execute("INSERT INTO events (username, event_name, event_date, event_end_date, event_category, event_time, event_end_time, event_city, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (creator_username, event_name, event_date, event_end_date, event_category, event_time, event_end_time, event_city, note)) 
          events_db.commit()

          events_cursor.execute("SELECT * FROM events WHERE event_name = ?", (event_name,))
          dup_check = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE username = ?", (creator_username,))
          dup_check1 = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE event_date = ?", (event_date,))
          dup_check2 = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE event_end_date = ?", (event_end_date,))
          dup_check3 = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE event_time = ?", (event_time,))
          dup_check4 = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE event_end_time = ?", (event_end_time,))
          dup_check5 = users_cursor.fetchone()
          events_cursor.execute("SELECT * FROM events WHERE event_city = ?", (event_city,))
          dup_check6 = users_cursor.fetchone()


          now_day=dt.datetime.now().day # 
          now_month=dt.datetime.now().month # 
          now_year=dt.datetime.now().year #
          now_hour=dt.datetime.now().hour
          now_minute=dt.datetime.now().minute
          print(now_day)
          print(now_month)
          print(now_year)

          event_date_parts = event_date.split('/')
          event_date_day = int(event_date_parts[0])
          event_date_month = int(event_date_parts[1])
          event_date_year = int(event_date_parts[2])
          print(event_date_day)
          print(event_date_month)
          print(event_date_year)


          event_time_parts = event_time.split(':')
          event_time_hour = int(event_time_parts[0])
          event_time_minute = int(event_time_parts[1])

          event_end_date_parts = event_end_date.split('/')
          event_end_date_day = int(event_end_date_parts[0])
          event_end_date_month = int(event_end_date_parts[1])
          event_end_date_year = int(event_end_date_parts[2])
          print(event_end_date_day)
          print(event_end_date_month)
          print(event_end_date_year)



          event_end_time_parts = event_end_time.split(':')
          event_end_time_hour = int(event_end_time_parts[0])
          event_end_time_minute = int(event_end_time_parts[1])


          if not event_name:
            event_status_label.config(text="Event name cannot be empty.")
            return
      
          elif not event_date:
            event_status_label.config(text="Event date cannot be empty.")
            return
           
          elif not event_end_date:
            event_status_label.config(text="Event end date cannot be empty.")
            return
          
          elif not event_time:
            event_status_label.config(text="Event time cannot be empty.")
            return
          elif not event_end_time:
            event_status_label.config(text="Event end time cannot be empty.")
            return
          
          elif not event_city:
            event_status_label.config(text="Event city cannot be empty.")
            return
           
          elif dup_check and dup_check1 and dup_check2 and dup_check3 and dup_check4 and dup_check5 and dup_check6:
            event_status_label.config(text="This event has already been created.")
            return

          elif event_end_date_year < event_date_year:
            event_status_label.config(text="Please choose valid start and end dates for the event.")
            return

          elif event_end_date_year == event_date_year and event_end_date_month < event_date_month:
            event_status_label.config(text="Please choose a valid event date.")
            return

          elif event_end_date_year == event_date_year and event_end_date_month == event_date_month and event_end_date_day < event_date_day:
            event_status_label.config(text="Please choose a valid event date.")
            return

          elif event_end_date_year == event_date_year and event_end_date_month == event_date_month and event_end_date_day == event_date_day and event_end_time_parts < event_time_parts:
            event_status_label.config(text="Please choose a valid event date.")
            return

          elif event_end_date_year == event_date_year and event_end_date_month == event_date_month and event_end_date_day == event_date_day and event_end_time_parts == event_time_parts and event_end_time_minute < event_time_minute:
            event_status_label.config(text="Please choose a valid event date.")
            return

          elif event_date_year < now_year or event_date_year > now_year + 100:
            event_status_label.config(text="Event date can't be before today or too far in the future.")
            return

          elif event_date_year == now_year and event_date_month < now_month:
            event_status_label.config(text="Event date can't be before today.")
            return

          elif event_date_year == now_year and event_date_month == now_month and event_date_day < now_day:
            event_status_label.config(text="Event date can't be before today.")
            return

          elif event_date_year == now_year and event_date_month == now_month and event_date_day == now_day and event_time_hour < now_hour:
            event_status_label.config(text="Event date can't be before today.")
            return

          elif event_date_year == now_year and event_date_month == now_month and event_date_day == now_day and event_time_hour == now_hour and event_time_minute < now_minute:
            event_status_label.config(text="Event date can't be before today.")
            return


          else:
            
            events_cursor.execute("INSERT INTO events (username, event_name, event_date, event_end_date, event_category, event_time, event_end_time, event_city, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (creator_username, event_name, event_date, event_end_date, event_category, event_time, event_end_time, event_city, note)) 
            events_db.commit()
            event_status_label.config(text="Your event was saved successfully.")
      create_event_button ["command"] = save_event
      create_event_button.pack()








def open_sign_up_window():

     
    auth_window = Toplevel()
    header_label = Label(auth_window, text="Sign Up")
    header_label.pack()
    #main_window.withdraw()
    auth_window.geometry("1024x1024")

    # Sign-up section
    sign_up_title_label = ttk.Label(auth_window, text="Sign Up", font=("Arial", 16, "bold"))
    sign_up_title_label.pack(pady=10)


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
    
    Label11= Label(auth_window, text="Sports you're interested in:")
    Athletics = Checkbutton(auth_window, text = "Athletics", variable = CheckVar1, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20, )
    Gymnastics = Checkbutton(auth_window, text = "Gymnastics", variable = CheckVar2, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    MotorSports = Checkbutton(auth_window, text = "Motor Sports", variable = CheckVar3, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    TeamSports = Checkbutton(auth_window, text = "Team Sports", variable = CheckVar4, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    RacketSports = Checkbutton(auth_window, text = "Racket Sports", variable = CheckVar5, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    CombatSports = Checkbutton(auth_window, text = "Combat Sports", variable = CheckVar6, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    WaterSports = Checkbutton(auth_window, text = "Water Sports", variable = CheckVar7, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    AnimalSports = Checkbutton(auth_window, text = "Animal Sports", variable = CheckVar8, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    ExtremeSports = Checkbutton(auth_window, text = "Extreme Sports", variable = CheckVar9, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    WinterSports = Checkbutton(auth_window, text = "Winter Sports", variable = CheckVar10, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    WheelSports= Checkbutton(auth_window, text = "Wheel Sports", variable = CheckVar11, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    TargetSports = Checkbutton(auth_window, text = "Target Sports", variable = CheckVar12, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    ESports = Checkbutton(auth_window, text = "E-Sports", variable = CheckVar13, \
    onvalue = 1, offvalue = 0, height=1, \
    width = 20)
    Label11.pack()
    Athletics.pack()
    Gymnastics.pack()
    MotorSports.pack()
    TeamSports.pack()
    RacketSports.pack()
    CombatSports.pack()
    WaterSports.pack()
    AnimalSports.pack()
    ExtremeSports.pack()
    WinterSports.pack()
    WheelSports.pack()
    TargetSports.pack()
    ESports.pack()


    Athletics = str(Athletics)
    Gymnastics = str(Gymnastics)
    MotorSports = str(MotorSports)
    TeamSports = str(TeamSports)
    RacketSports = str(RacketSports)
    CombatSports = str(CombatSports)
    WaterSports = str(WaterSports)
    AnimalSports = str(AnimalSports)
    ExtremeSports = str(ExtremeSports)
    WinterSports = str(WinterSports)
    WheelSports = str(WheelSports)
    TargetSports = str(TargetSports)
    ESports = str(ESports)

    # Username label and input field
    signup_username_label = ttk.Label(auth_window, text="Username:")
    signup_username_label.pack()
    signup_username_entry = ttk.Entry(auth_window)
    signup_username_entry.pack()

    # Password label and input field
    signup_password_label = ttk.Label(auth_window, text="Password:")
    signup_password_label.pack()
    signup_password_entry = ttk.Entry(auth_window, show="*")
    signup_password_entry.pack()

    # Repeat-password label and input field
    signup_password2_label = ttk.Label(auth_window, text="Password (Again):")
    signup_password2_label.pack()
    signup_password2_entry = ttk.Entry(auth_window, show="*")
    signup_password2_entry.pack()

    # Email label and input field
    email_label = ttk.Label(auth_window, text="Email:")
    email_label.pack()
    email_entry = ttk.Entry(auth_window)
    email_entry.pack()
   
    # Full name label and input field
    full_name_label = ttk.Label(auth_window, text="Full Name:")
    full_name_label.pack()
    full_name_entry = ttk.Entry(auth_window)
    full_name_entry.pack()

    # Date of birth label and input field
    birth_date_label = ttk.Label(auth_window, text="Date of Birth:")
    birth_date_label.pack()
    birth_date_entry = ttk.Entry(auth_window)
    #birth_date_entry.pack()
    #now=dt.datetime.now()
    current_day=dt.datetime.now().day # 
    current_month=dt.datetime.now().month # 
    current_year=dt.datetime.now().year # 
    
    
    # Add Calendar
    cal = Calendar(auth_window, selectmode = 'day',
                year = (current_year-15), month = current_month,
                day = current_day, birth_year = current_month and current_day)
 
    cal.pack(pady = 0)




    date = Label(auth_window, text = "")
    date.pack(pady = 0)
    # Sign-up button
    sign_up_button = ttk.Button(auth_window, text="Sign Up")
    sign_up_button.pack(pady=0)

    result_label1 = ttk.Label(auth_window, text="")
    result_label1.pack(pady=0)

    

    def register():
    


        username = signup_username_entry.get()
        password = signup_password_entry.get()
        password_repeat = signup_password2_entry.get()
        email = email_entry.get()
        full_name = full_name_entry.get()
        birth_date = cal.get_date()
    
        birth_date=dt.datetime.strptime(birth_date,"%m/%d/%y")
        now=dt.datetime.now()
        age_delta=now-birth_date 
        age_years=age_delta.days//365
        #if age_years < 0:
        #age_years = (age_years*(-1))
        email_str=str(email)
        index=0
        count=0
        while index < (len(email_str)-1):
           index += 1
           if email_str[index]=="@":
               count+= 1

        users_cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        data = users_cursor.fetchone()
        users_cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        email_check = users_cursor.fetchone()
        # Check whether the username is empty
        if not username:
            result_label1.config(text="Username cannot be empty.")
            return
        
            # Check whether the password is empty
        elif not password:
            result_label1.config(text="Password cannot be empty.")
            return
            # Check whether the passwords match
        elif password != password_repeat:
            result_label1.config(text="Passwords do not match.")
            return
            # Check whether the username is already used in the database
        elif data:
            result_label1.config(text="This username is already taken.")
        elif email_check:
            result_label1.config(text="This email is already in use.")
        elif count !=1:
            result_label1.config(text="please enter a valid email address.")
        elif (age_years < 15 or age_years > 123):
            result_label1.config(text=age_years)
            #result_label1.config(text="You are not within the age range required to use this app.")
        else:
            # Add the new user to the database
            users_cursor.execute("INSERT INTO users (username, password, email, full_name, birth_date, Athletics, Gymnastics, MotorSports, TeamSports, RacketSports, CombatSports, WaterSports, AnimalSports, ExtremeSports, WinterSports, WheelSports, TargetSports, ESports) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )",
                   (username, password, email, full_name, birth_date, CheckVar1.get(), CheckVar2.get(), CheckVar3.get(), CheckVar4.get(), CheckVar5.get(), CheckVar6.get(), CheckVar7.get(), CheckVar8.get(), CheckVar9.get(), CheckVar10.get(), CheckVar11.get(), CheckVar12.get(), CheckVar13.get())) 
            users_db.commit()
            result_label1.config(text="Account created successfully.")
            sign_up_button["command"] = register


        users_cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        data = users_cursor.fetchone()
        users_cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        email_check = users_cursor.fetchone()
        # Check whether the username is empty
        if not username:
            result_label1.config(text="Username cannot be empty.")
            return
        
            # Check whether the password is empty
        elif not password:
            result_label1.config(text="Password cannot be empty.")
            return
            # Check whether the passwords match
        elif password != password_repeat:
            result_label1.config(text="Passwords do not match.")
            return
            # Check whether the username is already used in the database
        elif data:
            result_label1.config(text="This username is already taken.")
        elif email_check:
            result_label1.config(text="This email is already in use.")
        elif count !=1:
            result_label1.config(text="please enter a valid email address.")
        elif (age_years < 15 or age_years > 123):
            result_label1.config(text=age_years)
            #result_label1.config(text="You are not within the age range required to use this app.")
        else:
            # Add the new user to the database
            users_cursor.execute("INSERT INTO users (username, password, email, full_name, birth_date, Athletics, Gymnastics, MotorSports, TeamSports, RacketSports, CombatSports, WaterSports, AnimalSports, ExtremeSports, WinterSports, WheelSports, TargetSports, ESports) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? )",
                   (username, password, email, full_name, birth_date, CheckVar1.get(), CheckVar2.get(), CheckVar3.get(), CheckVar4.get(), CheckVar5.get(), CheckVar6.get(), CheckVar7.get(), CheckVar8.get(), CheckVar9.get(), CheckVar10.get(), CheckVar11.get(), CheckVar12.get(), CheckVar13.get())) 
            users_db.commit()
            result_label1.config(text="Account created successfully.")
    sign_up_button["command"] = register
 




# Set screensize as fullscreen and not resizable
main_window.geometry("1024x1024")
main_window.resizable(False, False)


# Add Connect, Share, Inspire! slogan next to the button frame
imgconnect = Image.open("C:/Users/Admin/Downloads/sporting-goods-volleyball-coach-badminton-removebg-preview (1).png")
img2 = ImageTk.PhotoImage(imgconnect)
imgconnect = imgconnect.resize((550, 500))
img2 = ImageTk.PhotoImage(imgconnect)


label = Label(main_window, image=img2, bg="#FFFDD0", borderwidth=0)
label.place(x=50, y=175)



# Add Sign Up and Sign In buttons with improved style
style = ttk.Style()
style.configure('TButton', relief=RAISED, font=('Arial', 20), padding=10)
style.map('TButton', foreground=[('active', 'white')], background=[('active', 'light blue')])

# Create a frame for buttons
button_frame = Frame(main_window, bg='moccasin', bd=2, relief = RAISED)
button_frame.place(x=1000, y=150, width=400, height=550, anchor='ne')

signup_button = ttk.Button(button_frame, text='Sign Up', style='TButton', command=open_sign_up_window)
signup_button.place(x=117, y=250)

signin_button = ttk.Button(button_frame, text='Sign In', style='TButton', command=open_sign_in_window)
signin_button.place(x=117, y=350)

# Add SocialCircle label at the top-left corner
imgSC = Image.open("C:/Users/Admin/Desktop/Python/SC.png")
img1 = ImageTk.PhotoImage(imgSC)
imgSC = imgSC.resize((150,150))
img1 = ImageTk.PhotoImage(imgSC)


label = Label(main_window, image=img1, bg="#FFFFFF", borderwidth=0)

label.place(x=735, y=180)




# Create a cursor so we can run operations on the database
users_cursor = users_db.cursor()


# Use the cursor's execute() method to create a table called users
# This table has username, password, email, full_name, birth_date and one column per sport category
users_cursor.execute("""CREATE TABLE IF NOT EXISTS users
    (username TEXT, password TEXT, email TEXT, full_name TEXT, birth_date TEXT, Athletics TEXT ,Gymnastics TEXT ,MotorSports TEXT ,TeamSports TEXT ,RacketSports TEXT ,CombatSports TEXT ,
WaterSports TEXT ,AnimalSports TEXT ,ExtremeSports TEXT ,WinterSports TEXT ,WheelSports TEXT ,TargetSports TEXT ,ESports TEXT)""")




# Save the changes we made
users_db.commit()

events_cursor = events_db.cursor()

events_cursor.execute("""CREATE TABLE IF NOT EXISTS events
    (username TEXT, event_name TEXT, event_date TEXT, event_end_date TEXT, event_category TEXT, event_time TEXT, event_end_time TEXT, event_city TEXT, note TEXT)""")


events_db.commit()

main_window.mainloop()