# only changes
length_of_road_vision = 0.09

slowest_vehicle_speed = 15
maximum_count = 80
fastest_vehicle_speed = 60
total_vehicle_bias = 1
average_speed_bias = 1 / 3
average_speed_traffic = 30

current = 0

timeout_signal_time = 30
data_sending_time = 5
data_retrieval_time = 10
maximum_time_for_signal = 60
minimum_time_for_signal = data_sending_time + data_retrieval_time #should be greater than data_retrieval_time + data_sending_time

#from cv2 import imshow, waitKey
from cv2 import rectangle, cvtColor, COLOR_BGR2RGB, VideoCapture, destroyAllWindows
from cvzone import putTextRect
from ultralytics import YOLO
from pandas import DataFrame, read_excel
from collections import Counter
from glob import glob
from time import sleep, time
from firebase_admin import credentials, firestore,initialize_app
from numpy import full, where
from contextlib import contextmanager
from json import loads, load
from PIL import Image
from io import BytesIO
from base64 import b64encode
from dotenv import load_dotenv
import os

node = 9
signal = 4
emergency = 0
emergency_vehicle_signal = []
image_path = "IMAGE AND VIDEO/image.jpg"

with open('VEHICLE LIST/vehicle_speed.json', 'r') as f:
    vehicle_speed = load(f)
with open('VEHICLE LIST/emergency_vehicle_list.txt', 'r') as f:
    emergency_vehicle_list = f.read().splitlines()
with open('VEHICLE LIST/accident_vehicle_list.txt', 'r') as f:
    accident_vehicle_list = f.read().splitlines()

    
direction = {direction: i for i, direction in enumerate(["n", "e", "s", "w", "ne", "se", "nw", "sw"])}

dir_dis = read_excel(f"DIRECTION AND DISTANCE/a{current}.xlsx")

model = YOLO("MODEL/best.pt")

my_file = open("LABEL/label.txt", "r")
data = my_file.read()
class_list = data.split("\n")


def read_image(image_path):
    with open(image_path, 'rb') as image_file:
        image = Image.open(image_file)
        image_bytes = BytesIO()
        image.save(image_bytes, format=image.format)
        image_bytes = image_bytes.getvalue()
        
        image_base64 = b64encode(image_bytes).decode('utf-8')
        
        return image_bytes, image_base64
        
def frame_to_base64(frame):
    # Convert the frame to a PIL Image
    image = Image.fromarray(cvtColor(frame, COLOR_BGR2RGB))

    # Save the image to a byte buffer
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    byte_data = buffer.getvalue()

    # Encode the byte data to base64
    base64_str = b64encode(byte_data).decode('utf-8')

    return base64_str


def object(img):
    results = model.predict(img)
    a = results[0].boxes.data
    #px = DataFrame(a).astype("float")
    px = DataFrame(a.cpu()).astype("float")
    object_classes = []

    for index, row in px.iterrows():
        x1=int(row[0])
        y1=int(row[1])
        x2=int(row[2])
        y2=int(row[3])
        d=int(row[5])
        obj_class = class_list[d]
        if(obj_class in vehicle_count_empty.keys()):
            object_classes.append(obj_class)
            rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), 2)
            putTextRect(img, f'{obj_class}', (x2, y2), 1, 1)
    base_64 = frame_to_base64(img)
    #imshow("Traffic monitoring",img)
    #k = waitKey(0)
    #if(k==27):
    #   destroyAllWindows()
    
    #list in form --> ['car', 'car', 'car', 'car', 'bus'] for each signal of each node
    return base_64, object_classes


        
#this function takes the above list and creates a dictionary for each vehicle and its count and update it against given signal of given node
def count_objects_in_image(base_64, object_classes,direction_val):
    vehicle_count_send = vehicle_count_empty.copy()
    counter = Counter(object_classes)
    for vec, count in counter.items():
        if(vec in vehicle_count_send.keys()):
            vehicle_count_send[vec] = count
    vehicle_count_send['base_64']=base_64
    doc_ref = db.collection(f'traffic_{current}').document(f'count_{direction_val}')
    try:
        doc_ref.update(vehicle_count_send)
    except Exception as e:
        doc_ref.set(vehicle_count_send)
    del vehicle_count_send



load_dotenv(os.path.join("TRAFFIC KEY", ".env"))

firebase_config_json = loads(os.getenv("data"))

# Convert dictionary to Firebase credentials object
cred = credentials.Certificate(firebase_config_json)
try:
    initialize_app(cred)
    db = firestore.client()
except Exception as e:
    pass
    
doc_accident = db.collection(f'accident').document(f'node_{current}')

#this function will stop a function to run if it exceeds certain time period
@contextmanager
def timeout(seconds):
    start_time = time()
    yield
    elapsed_time = time() - start_time
    if elapsed_time > seconds:
        raise TimeoutError("Timeout exceeded")

def map_value(value, old_min, old_max, new_min, new_max):
    return ((value - old_min) * (new_max - new_min) / (old_max - old_min)) + new_min

# this func calculate signal change value for other signal that can affect the current signal
def sig_change():
    global emergency
    north, east, south, west = 0, 0, 0, 0
    
    for i in range(node):
        if(i == current):
            continue
        doc=db.collection(f'traffic_{i}')
        all_signal_count_vehicle=[0,0,0,0]
        if(doc is not None):
            for j in range(signal):
                all_signal_vehicle = doc.document(f'count_{j}').get().to_dict()
                try:
                    del all_signal_vehicle['base_64']
                except Exception as e:
                    pass  
                if all_signal_vehicle:
                    all_signal_count_vehicle[j] = sum(all_signal_vehicle.values())
                else:
                    all_signal_count_vehicle[j] = 0
        index_val = int(where(dir_dis["point"] == f"a{i}")[0].item())
        signal_dir = int(dir_dis.loc[index_val, "direction"])
        signal_dis = int(dir_dis.loc[index_val, "distance"])
        #for the current point(current) other point (i) is nw  of current so only nw traffic should be considered 
        if(signal_dir == direction["n"]):   # N
            north += sum([value for index, value in enumerate(all_signal_count_vehicle) if index == direction["n"]]) / (signal_dis * 2)
        elif(signal_dir == direction["e"]):   # E
            east += sum([value for index, value in enumerate(all_signal_count_vehicle) if index == direction["e"]]) / (signal_dis * 2)
        elif(signal_dir == direction["s"]):   # S
            south += sum([value for index, value in enumerate(all_signal_count_vehicle) if index == direction["s"]]) / (signal_dis * 2)
        elif(signal_dir == direction["w"]):   # W
            west += sum([value for index, value in enumerate(all_signal_count_vehicle) if index == direction["w"]]) / (signal_dis * 2)
        elif(signal_dir == direction["ne"]):   # NE
            east += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["n"] | index == direction["e"])]) / 2) / (signal_dis * 2)
            north += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["n"] | index == direction["e"])]) / 2) / (signal_dis * 2)
        elif(signal_dir == direction["se"]):   # SE
            east += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["s"] | index == direction["e"])]) / 2) / (signal_dis * 2)
            south += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["s"] | index == direction["e"])]) / 2) / (signal_dis * 2)
        elif signal_dir == direction["nw"]:   # NW
            west += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["n"] | index == direction["w"])]) / 2) / (signal_dis * 2)
            north += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["n"] | index == direction["w"])]) / 2) / (signal_dis * 2)
        elif signal_dir == direction["sw"]:   # SW
            south += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["s"] | index == direction["w"])]) / 2) / (signal_dis * 2)
            west += (sum([value for index, value in enumerate(all_signal_count_vehicle) if (index == direction["s"] | index == direction["w"])]) / 2) / (signal_dis * 2)  
        del all_signal_count_vehicle


    doc=db.collection(f'traffic_{current}')
    all_signal_count_vehicle = [0,0,0,0]
    average_speed = average_speed_traffic  # in km/hr
    net_vehicle_count = {key: 0 for key in vehicle_speed}
    total_time = 0.0
    total_distance = 0.0
    if(doc is not None):
        for j in range(signal):
            all_signal_vehicle = doc.document(f'count_{j}').get().to_dict()
            try:
                del all_signal_vehicle['base_64']
            except Exception as e:
                pass  
            if all_signal_vehicle:
                for key in all_signal_vehicle.keys():
                    if(key in accident_vehicle_list):
                        try:
                            doc_accident.update({"accident": 1})
                        except Exception as e:
                            doc_accident.set({"accident": 1})
                    else:
                        try:
                            doc_accident.update({"accident": 0})
                        except Exception as e:
                            doc_accident.set({"accident": 0})
                    if(key in emergency_vehicle_list):
                        emergency = db.collection("emergency").document(f'node_{current}').get().to_dict()["emergency"]
                        emergency_vehicle_signal.append(j)
                    else:
                        emergency = 0
                    if(key in vehicle_speed.keys()):
                        net_vehicle_count[key] += all_signal_vehicle[key]

                
                all_signal_count_vehicle[j] = sum(all_signal_vehicle.values())
            else:
                all_signal_count_vehicle[j] = 0

        for vehicle_name, count in net_vehicle_count.items():
                total_time += (length_of_road_vision/vehicle_speed[vehicle_name]) * count
                total_distance += (length_of_road_vision * count)
        if(total_time != 0):
            average_speed = (total_distance / total_time) 
    total_vehicle = min(sum(net_vehicle_count.values()), maximum_count)
    del net_vehicle_count
    
    calculated_time_allowed = ((total_vehicle ** total_vehicle_bias)/(average_speed ** average_speed_bias))  
    old_max = (maximum_count ** total_vehicle_bias) / (slowest_vehicle_speed ** average_speed_bias)
    old_min = 1 / (fastest_vehicle_speed ** average_speed_bias)
    new_min = minimum_time_for_signal * 4
    new_max = maximum_time_for_signal * 4
    
    maximum_time_allowed = map_value(calculated_time_allowed, old_min, old_max, new_min, new_max)             
    
    north += all_signal_count_vehicle[direction["n"]]
    east += all_signal_count_vehicle[direction["e"]]
    south += all_signal_count_vehicle[direction["s"]]
    west += all_signal_count_vehicle[direction["w"]]
    del all_signal_count_vehicle
    
    net_cars = north + east + south + west
    
    if(net_cars == 0):
        north = minimum_time_for_signal
        east = minimum_time_for_signal
        south = minimum_time_for_signal
        west = minimum_time_for_signal
    else:
        north = int((north / net_cars) * maximum_time_allowed)
        east = int((east / net_cars) * maximum_time_allowed) 
        south = int((south / net_cars) * maximum_time_allowed)
        west = int((west / net_cars) * maximum_time_allowed)
        if(north == 0):
            north = minimum_time_for_signal
        if(east == 0):
            east = minimum_time_for_signal
        if(south == 0):
            south = minimum_time_for_signal
        if(west == 0):
            west = minimum_time_for_signal
    return (north, east, south, west)



with open('VEHICLE LIST/vehicle_list.json', 'r') as f:
    vehicle_count_empty = load(f) 

cap0 = VideoCapture("IMAGE AND VIDEO/video1.mp4")  
cap1 = VideoCapture("IMAGE AND VIDEO/video2.mp4")  
cap2 = VideoCapture("IMAGE AND VIDEO/video3.mp4")  
cap3 = VideoCapture("IMAGE AND VIDEO/video4.mp4")  


signal_green = 0   # start system from north


for current_direction in range(signal):
    try: 
        collection_ref = db.collection(f'traffic_{current}').document(f'count_{current_direction}').delete()  
    except Exception as e:
        pass
    image_bytes, image_base64 = read_image(image_path)
    vehicle_count_empty['base_64'] = image_base64 
    doc_ref = db.collection(f'traffic_{current}').document(f'count_{current_direction}')
    try:
        doc_ref.update(vehicle_count_empty)
    except Exception as e:
        doc_ref.set(vehicle_count_empty)

k = 1

ret0,frame0 = cap0.read()    
ret1,frame1 = cap1.read()
ret2,frame2 = cap2.read()
ret3,frame3 = cap3.read()

if frame0 is None or frame1 is None or frame2 is None or frame3 is None:
    print("One or more frames failed to capture. Skipping this iteration or terminating loop.")
    os._exit(0)

for i in range(100):
    ret0,frame0 = cap0.read()    
    ret1,frame1 = cap1.read()
    ret2,frame2 = cap2.read()
    ret3,frame3 = cap3.read()
    
print("Signal North:", end="")
base_64, object_classes0 = object(frame0)
print("")
count_objects_in_image(base_64, object_classes0,direction_val = 0)
print("Signal East:", end="")
base_64, object_classes1 = object(frame1)
print("")
count_objects_in_image(base_64, object_classes1,direction_val = 1)
print("Signal South:", end="")
base_64, object_classes2 = object(frame2)
print("")
count_objects_in_image(base_64, object_classes2,direction_val = 2)
print("Signal West:", end="")
base_64, object_classes3 = object(frame3)
print("")
count_objects_in_image(base_64, object_classes3,direction_val = 3)

north, east, south, west = sig_change()
while True:
    if(signal_green == direction["n"]):
        # MAKE NORTH GREEN OTHER RED
        if(north < data_retrieval_time + data_sending_time):
            north = data_retrieval_time + data_sending_time
        print("\n\nNorth: Green\nEast: Red\nSouth: Red\nWest: Red\n")
        print("Signal Time:", north, end=" sec.\n\n")

        sleep(north - data_retrieval_time - data_sending_time)   
        t=time()
            
        ret0,frame0 = cap0.read()    
        ret1,frame1 = cap1.read()
        ret2,frame2 = cap2.read()
        ret3,frame3 = cap3.read()

        for i in range(50):
            ret0,frame0 = cap0.read()    
            ret1,frame1 = cap1.read()
            ret2,frame2 = cap2.read()
            ret3,frame3 = cap3.read()

        
        if frame0 is None or frame1 is None or frame2 is None or frame3 is None:
            print("One or more frames failed to capture. Skipping this iteration or terminating loop.")
            break

        
        print("Signal North:", end="")
        base_64, object_classes0 = object(frame0)
        print("")
        count_objects_in_image(base_64, object_classes0,direction_val = 0)
        print("Signal East:", end="")
        base_64, object_classes1 = object(frame1)
        print("")
        count_objects_in_image(base_64, object_classes1,direction_val = 1)
        print("Signal South:", end="")
        base_64, object_classes2 = object(frame2)
        print("")
        count_objects_in_image(base_64, object_classes2,direction_val = 2)
        print("Signal West:", end="")
        base_64, object_classes3 = object(frame3)
        print("")
        count_objects_in_image(base_64, object_classes3,direction_val = 3)
        
        try:
            with timeout(data_retrieval_time):
                north, east, south, west = sig_change()
        except TimeoutError as e:
            east = timeout_signal_time
            print("Data retrieval from database timeout, East", east)
            
        while(bool(emergency == 1) and signal_green in emergency_vehicle_signal):
            sleep(10)
            north, east, south, west = sig_change()
        try:
            emergency_vehicle_signal.pop(signal)
        except Exception as e:
            pass   
        sleep((data_retrieval_time + data_sending_time - (time() - t)) if (data_retrieval_time - (time() - t)) > 0 else 0)
        #MAKE NORTH AND EAST YELLOW
        print("\n\nNorth: Yellow\nEast: Yellow\nSouth: Red\nWest: Red\n")
        print("Signal Time: 2 sec.", end="\n\n")
        sleep(2)


    
    elif(signal_green == direction["e"]):
        # MAKE EAST GREEN OTHER RED
        if(east < data_retrieval_time + data_sending_time):
            east = data_retrieval_time + data_sending_time
        print("\n\nNorth: Red\nEast: Green\nSouth: Red\nWest: Red\n")
        print("Signal Time:", east, end=" sec.\n\n")
        sleep(east - data_retrieval_time - data_sending_time)   
        t=time()
        
        ret0,frame0 = cap0.read()    
        ret1,frame1 = cap1.read()
        ret2,frame2 = cap2.read()
        ret3,frame3 = cap3.read()
        
        for i in range(50):
            ret0,frame0 = cap0.read()    
            ret1,frame1 = cap1.read()
            ret2,frame2 = cap2.read()
            ret3,frame3 = cap3.read()

        
        if frame0 is None or frame1 is None or frame2 is None or frame3 is None:
            print("One or more frames failed to capture. Skipping this iteration or terminating loop.")
            break
          
        print("Signal North:", end="")
        base_64, object_classes0 = object(frame0)
        print("")
        count_objects_in_image(base_64, object_classes0,direction_val = 0)
        print("Signal East:", end="")
        base_64, object_classes1 = object(frame1)
        print("")
        count_objects_in_image(base_64, object_classes1,direction_val = 1)
        print("Signal South:", end="")
        base_64, object_classes2 = object(frame2)
        print("")
        count_objects_in_image(base_64, object_classes2,direction_val = 2)
        print("Signal West:", end="")
        base_64, object_classes3 = object(frame3)
        print("")
        count_objects_in_image(base_64, object_classes3,direction_val = 3)
            
        try:
            with timeout(data_retrieval_time):
                north, east, south, west = sig_change()
        except TimeoutError as e:
            south = timeout_signal_time
            print("Data retrieval from database timeout, South", south)
            
        while(emergency == 1 and signal_green in emergency_vehicle_signal):
            sleep(10)
            north, east, south, west = sig_change()
        try:
            emergency_vehicle_signal.pop(signal)
        except Exception as e:
            pass
        sleep((data_retrieval_time + data_sending_time - (time() - t)) if (data_retrieval_time - (time() - t)) > 0 else 0)
        #MAKE SOUTH AND EAST YELLOW
        print("\n\nNorth: Red\nEast: Yellow\nSouth: Yellow\nWest: Red\n")
        print("Signal Time: 2 sec.", end="\n\n")
        sleep(2)

    
    elif(signal_green == direction["s"]):
        # MAKE SOUTH GREEN OTHER RED
        if(south < data_retrieval_time + data_sending_time):
            south = data_retrieval_time + data_sending_time
        print("\n\nNorth: Red\nEast: Red\nSouth: Green\nWest: Red\n")
        print("Signal Time:", south, end=" sec.\n\n")
        sleep(south - data_retrieval_time - data_sending_time)   
        t=time()
        ret0,frame0 = cap0.read()    
        ret1,frame1 = cap1.read()
        ret2,frame2 = cap2.read()
        ret3,frame3 = cap3.read()
        
        for i in range(50):
            ret0,frame0 = cap0.read()    
            ret1,frame1 = cap1.read()
            ret2,frame2 = cap2.read()
            ret3,frame3 = cap3.read()

        
        if frame0 is None or frame1 is None or frame2 is None or frame3 is None:
            print("One or more frames failed to capture. Skipping this iteration or terminating loop.")
            break 
          
        print("Signal North:", end="")
        base_64, object_classes0 = object(frame0)
        print("")
        count_objects_in_image(base_64, object_classes0,direction_val = 0)
        print("Signal East:", end="")
        base_64, object_classes1 = object(frame1)
        print("")
        count_objects_in_image(base_64, object_classes1,direction_val = 1)
        print("Signal South:", end="")
        base_64, object_classes2 = object(frame2)
        print("")
        count_objects_in_image(base_64, object_classes2,direction_val = 2)
        print("Signal West:", end="")
        base_64, object_classes3 = object(frame3)
        print("")
        count_objects_in_image(base_64, object_classes3,direction_val = 3)
          
        try:
            with timeout(data_retrieval_time):
                north, east, south, west = sig_change()
        except TimeoutError as e:
            west = timeout_signal_time
            print("Data retrieval from database timeout, West", west)
            
        while(emergency == 1 and signal_green in emergency_vehicle_signal):
            sleep(10)
            north, east, south, west = sig_change()
        try:
            emergency_vehicle_signal.pop(signal)
        except Exception as e:
            pass
        sleep((data_retrieval_time + data_sending_time - (time() - t)) if (data_retrieval_time - (time() - t)) > 0 else 0)
        #MAKE SOUTH AND WEST YELLOW
        print("\n\nNorth: Red\nEast: Red\nSouth: Yellow\nWest: Yellow\n")
        print("Signal Time: 2 sec.", end="\n\n")
        sleep(2)
    elif(signal_green == direction["w"]):
        # MAKE WEST GREEN OTHER RED
        if(west < data_retrieval_time + data_sending_time):
            west = data_retrieval_time + data_sending_time
        print("\n\nNorth: Red\nEast: Red\nSouth: Red\nWest: Green\n")
        print("Signal Time:", west, end=" sec.\n\n")
        sleep(west - data_retrieval_time - data_sending_time)   
        t=time()
        
        ret0,frame0 = cap0.read()    
        ret1,frame1 = cap1.read()
        ret2,frame2 = cap2.read()
        ret3,frame3 = cap3.read()
        
        for i in range(50):
            ret0,frame0 = cap0.read()    
            ret1,frame1 = cap1.read()
            ret2,frame2 = cap2.read()
            ret3,frame3 = cap3.read()

        
        if frame0 is None or frame1 is None or frame2 is None or frame3 is None:
            print("One or more frames failed to capture. Skipping this iteration or terminating loop.")
            break
          
        print("Signal North:", end="")
        base_64, object_classes0 = object(frame0)
        print("")
        count_objects_in_image(base_64, object_classes0,direction_val = 0)
        print("Signal East:")
        base_64, object_classes1 = object(frame1)
        print("")
        count_objects_in_image(base_64, object_classes1,direction_val = 1)
        print("Signal South:", end="")
        base_64, object_classes2 = object(frame2)
        print("")
        count_objects_in_image(base_64, object_classes2,direction_val = 2)
        print("Signal West:", end="")
        base_64, object_classes3 = object(frame3)
        print("")
        count_objects_in_image(base_64, object_classes3,direction_val = 3)
          
        try:
            with timeout(data_retrieval_time):
                north, east, south, west = sig_change()
        except TimeoutError as e:
            north = timeout_signal_time
            print("Data retrieval from database timeout, North", north)
            
        while(emergency == 1 and signal_green in emergency_vehicle_signal):
            sleep(10)
            north, east, south, west = sig_change()
        try:
            emergency_vehicle_signal.pop(signal)
        except Exception as e:
            pass
        sleep((data_retrieval_time + data_sending_time - (time() - t)) if (data_retrieval_time - (time() - t)) > 0 else 0)
        #MAKE NORTH AND WEST YELLOW
        print("\n\nNorth: Yellow\nEast: Red\nSouth: Red\nWest: Yellow\n")
        print("Signal Time: 2 sec.", end="\n\n")
        sleep(2)
    signal_green = (signal_green + 1) % 4 

cap0.release()
cap1.release()
cap2.release()
cap3.release()
destroyAllWindows()
