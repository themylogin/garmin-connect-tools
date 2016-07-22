from __future__ import division

import argparse
import browsercookie
from geopy.distance import vincenty
import gpxpy.gpx
import math
import json
import re
import requests
import StringIO

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_or_url")
    parser.add_argument("name")
    args = parser.parse_args()

    session = requests.session()
    session.headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.106 Safari/537.36",
    }

    if re.match(r"https?://.+", args.file_or_url):
        response = session.post("http://www.gpsvisualizer.com/convert?output", data={
            "convert_format": "gpx",
            "remote_data": args.file_or_url,
        }).text
        m = re.search(r"/download/convert/([0-9\-]+)-data\.gpx", response)
        if m:
            gpx_file = StringIO.StringIO(session.get("http://www.gpsvisualizer.com" + m.group(0)).text)
        else:
            raise Exception("Unable to convert URL to GPX")
    else:
        gpx_file = open(args.file_or_url, "r")

    gpx = gpxpy.parse(gpx_file)

    session.cookies = browsercookie.chrome()
    for cookie in session.cookies:
        cookie.expires = None

    if len(gpx.tracks) > 1:
        individual_routes = raw_input("Route has %d tracks, make them individual routes? (1/0) " % len(gpx.tracks)) == "1"
    else:
        individual_routes = False

    if individual_routes:
        routes = [("%s %02d" % (args.name, i + 1), sum([segment.points for segment in track.segments], []))
                  for i, track in enumerate(gpx.tracks)]
    else:
        routes = [(args.name, sum([sum([segment.points for segment in track.segments], []) for track in gpx.tracks], []))]

    for name, route in routes:
        lines = []
        points = []
        distance = 0

        prev_point = None
        for point in route:
            if len(points) % 160 == 0:
                line = {"bearing": 0,
                        "distance": 0,
                        "startMarkerId": "marker-%d" % (len(lines) + 2),
                        "endMarkerId": "marker-%d" % (len(lines) + 3),
                        "points": []}
                lines.append(line)

            line["points"].append({"lat": point.latitude,
                                   "lon": point.longitude,
                                   "elevation": 0})
            points.append("%f,%f" % (point.latitude, point.longitude))

            if prev_point is not None:
                distance += vincenty(prev_point, (point.latitude, point.longitude)).meters / 1000

            prev_point = (point.latitude, point.longitude)

        form = session.get("https://connect.garmin.com/mincourse/create").text
        csrf_token = re.search(r'id="javax.faces.ViewState" value="(j_id[0-9]+)"', form).group(1)

        data = {
            "AJAXREQUEST": "_viewRoot",
            "courseForm:name": name,
            "courseForm:id": "",
            "courseForm:points": ";".join(points),
            "courseForm:lines": json.dumps(lines),
            "courseForm:description": "undefined",
            "courseForm:distance": str(distance),
            "courseForm:metric": "true",
            "courseForm:start": points[0],
            "courseForm:finish": points[-1],
            "courseForm:speed": "30",
            "courseForm:osm": "false",
            "courseForm": "courseForm",
            "autoScroll": "",
            "javax.faces.ViewState": csrf_token,
            "courseForm:saveRoute": "courseForm:saveRoute",
            "AJAX:EVENTS_COUNT":" 0",
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        response = session.post("https://connect.garmin.com/mincourse/create", data=data, headers=headers).text
        course_id = re.search('SELECTED_COURSE_ID = "([0-9]+)";', response).group(1)
        if course_id is None:
            raise Exception("Unable to create route %s" % name)
        else:
            print(name)
