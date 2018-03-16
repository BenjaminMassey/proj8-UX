"""
Open and close time calculations
for ACP-sanctioned brevets
following rules described at https://rusa.org/octime_alg.html
and https://rusa.org/pages/rulesForRiders
"""
import arrow, sys

#  Note for CIS 322 Fall 2016:
#  You MUST provide the following two functions
#  with these signatures, so that I can write
#  automated tests for grading.  You must keep
#  these signatures even if you don't use all the
#  same arguments.  Arguments are explained in the
#  javadoc comments.

chart = [[0, 15, 34], [200, 15, 32], [400, 15, 30],
         [600, 11.428, 28], [1000, 13.333, 26]]

def open_time(control_dist_km, brevet_dist_km, beginTime):
    """
    Args:
       control_dist_km:  number, the control distance in kilometers
       brevet_dist_km: number, the nominal distance of the brevet
           in kilometers, which must be one of 200, 300, 400, 600,
           or 1000 (the only official ACP brevet distances)
       brevet_start_time:  An ISO 8601 format date-time string indicating
           the official start time of the brevet
    Returns:
       An ISO 8601 format date string indicating the control open time.
       This will be in the same time zone as the brevet start time.
    """
    global chart

    total = 0
    
    for case in reversed(chart):
        if control_dist_km > case[0]:
            total += (control_dist_km - case[0]) / case[2]
            control_dist_km = case[0]

    splitTime = str(total).split(".")
    extraHours = int(splitTime[0])
    if len(splitTime) > 1:
        extraMinutes =  round(float("0." + splitTime[1]) * 60)
    else:
        extraMinutes = 0

    extraDays = 0
    
    while extraHours >= 24:
        extraHours -= 24
        extraDays += 1

    pieces = beginTime.split("T")
    date = pieces[0].split("-")
    time = pieces[1].split(":")
    beginYear = date[0]
    beginMonth = date[1]
    beginDay = date[2]
    beginHour = time[0]
    beginMin = time[1]
    
    year = int(beginYear)
    month = int(beginMonth)
    day = int(beginDay) + extraDays
    hour = int(beginHour) + extraHours
    minute = int(beginMin) + extraMinutes

    year = str(year)
    month = str(month)
    if len(month) < 2:
        month = "0" + month
    day = str(day)
    if len(day) < 2:
        day = "0" + day
    hour = str(hour)
    if len(hour) < 2:
        hour = "0" + hour
    minute = str(minute)
    if len(minute) < 2:
        minute = "0" + minute
    
    openTime = year+"-"+month+"-"+day+"T"+hour+":"+minute

    #print("OpenTIme =", openTime, file=sys.stderr)

    return openTime


def close_time(control_dist_km, brevet_dist_km, beginTime):
    """
    Args:
       control_dist_km:  number, the control distance in kilometers
          brevet_dist_km: number, the nominal distance of the brevet
          in kilometers, which must be one of 200, 300, 400, 600, or 1000
          (the only official ACP brevet distances)
       brevet_start_time:  An ISO 8601 format date-time string indicating
           the official start time of the brevet
    Returns:
       An ISO 8601 format date string indicating the control close time.
       This will be in the same time zone as the brevet start time.
    """
    global chart

    originalKm = control_dist_km
    
    total = 0
    
    for case in reversed(chart):
        if control_dist_km > case[0]:
            total += (control_dist_km - case[0]) / case[1]
            control_dist_km = case[0]

    splitTime = str(total).split(".")
    extraHours = int(splitTime[0])
    if len(splitTime) > 1:
        extraMinutes =  round(float("0." + splitTime[1]) * 60)
    else:
        extraMinutes = 0

    extraDays = 0

    if originalKm == 0:
        extraHours += 1
    
    while extraHours >= 24:
        extraHours -= 24
        extraDays += 1

    pieces = beginTime.split("T")
    date = pieces[0].split("-")
    time = pieces[1].split(":")
    beginYear = date[0]
    beginMonth = date[1]
    beginDay = date[2]
    beginHour = time[0]
    beginMin = time[1]

    year = int(beginYear)
    month = int(beginMonth)
    day = int(beginDay) + extraDays
    hour = int(beginHour) + extraHours
    minute = int(beginMin) + extraMinutes

    year = str(year)
    month = str(month)
    if len(month) < 2:
        month = "0" + month
    day = str(day)
    if len(day) < 2:
        day = "0" + day
    hour = str(hour)
    if len(hour) < 2:
        hour = "0" + hour
    minute = str(minute)
    if len(minute) < 2:
        minute = "0" + minute
    
    closeTime = year+"-"+month+"-"+day+"T"+hour+":"+minute

    #print("CloseTime =", closeTime, file=sys.stderr)
    
    return closeTime

