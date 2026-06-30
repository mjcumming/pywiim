"""WiiM API constants and mappings.

This module contains all API endpoint paths, field mappings, and SSL certificates
used for communicating with WiiM and LinkPlay devices.
"""

from __future__ import annotations

# SSL Certificate for WiiM devices (self-signed CA certificate)
WIIM_CA_CERT = """-----BEGIN CERTIFICATE-----
MIIDmDCCAoACAQEwDQYJKoZIhvcNAQELBQAwgZExCzAJBgNVBAYTAkNOMREwDwYD
VQQIDAhTaGFuZ2hhaTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtw
bGF5MQwwCgYDVQQLDANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAe
BgkqhkiG9w0BCQEWEW1haWxAbGlua3BsYXkuY29tMB4XDTE4MTExNTAzMzI1OVoX
DTQ2MDQwMTAzMzI1OVowgZExCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhTaGFuZ2hh
aTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtwbGF5MQwwCgYDVQQL
DANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAeBgkqhkiG9w0BCQEW
EW1haWxAbGlua3BsYXkuY29tMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEApP7trR9C8Ajr/CZqi70HYzQHZMX0gj8K3RzO0k5aucWiRkHtvcnfJIz+4dMB
EZHjv/STutsFBwbtD1iLEv48Cxvht6AFPuwTX45gYQ18hyEUC8wFhG7cW7Ek5HtZ
aLH75UFxrpl6zKn/Vy3SGL2wOd5qfBiJkGyZGgg78JxHVBZLidFuU6H6+fIyanwr
ejj8B5pz+KAui6T7SWA8u69UPbC4AmBLQxMPzIX/pirgtKZ7LedntanHlY7wrlAa
HroZOpKZxG6UnRCmw23RPHD6FUZq49f/zyxTFbTQe5NmjzG9wnKCf3R8Wgl8JPW9
4yAbOgslosTfdgrmjkPfFIP2JQIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQARmy6f
esrifhW5NM9i3xsEVp945iSXhqHgrtIROgrC7F1EIAyoIiBdaOvitZVtsYc7Ivys
QtyVmEGscyjuYTdfigvwTVVj2oCeFv1Xjf+t/kSuk6X3XYzaxPPnFG4nAe2VwghE
rbZG0K5l8iXM7Lm+ZdqQaAYVWsQDBG8lbczgkB9q5ed4zbDPf6Fsrsynxji/+xa4
9ARfyHlkCDBThGNnnl+QITtfOWxm/+eReILUQjhwX+UwbY07q/nUxLlK6yrzyjnn
wi2B2GovofQ/4icVZ3ecTqYK3q9gEtJi72V+dVHM9kSA4Upy28Y0U1v56uoqeWQ6
uc2m8y8O/hXPSfKd
-----END CERTIFICATE-----"""

# Audio Pro Client Certificate for Audio Pro MkII mutual TLS authentication
# Required for Audio Pro MkII/W-Series devices on port 4443
# Source: https://github.com/ramikg/linkplay-cli/blob/master/linkplay_cli/certs/linkplay_client.pem
# Original source: https://github.com/osk2/yamaha-soundbar/blob/master/custom_components/yamaha_soundbar/client.pem
#
# This certificate enables mutual TLS (mTLS) authentication with Audio Pro MkII devices
# Certificate issued by LinkPlay (www.linkplay.com) for client authentication
AUDIO_PRO_CLIENT_CERT = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCk/u2tH0LwCOv8
JmqLvQdjNAdkxfSCPwrdHM7STlq5xaJGQe29yd8kjP7h0wERkeO/9JO62wUHBu0P
WIsS/jwLG+G3oAU+7BNfjmBhDXyHIRQLzAWEbtxbsSTke1losfvlQXGumXrMqf9X
LdIYvbA53mp8GImQbJkaCDvwnEdUFkuJ0W5Tofr58jJqfCt6OPwHmnP4oC6LpPtJ
YDy7r1Q9sLgCYEtDEw/Mhf+mKuC0pnst52e1qceVjvCuUBoeuhk6kpnEbpSdEKbD
bdE8cPoVRmrj1//PLFMVtNB7k2aPMb3CcoJ/dHxaCXwk9b3jIBs6CyWixN92CuaO
Q98Ug/YlAgMBAAECggEAHyCpHlwjeL12J9/nge1rk1+hdXWTJ29VUVm5+xslKp8K
ek6912xaWL7w5xGzxejMGs69gCcJz8WSu65srmygT0g3UTkzRCetj/2AWU7+C1BG
Q+N9tvpjQDkvSJusxn+tkhbCp7n03N/FeGEAngJLWN+JH1hRu5mBWNPs2vvgyRAO
Cv95G7uENavCUXcyYsKPoAfz3ebD/idwwWW2RKAd0ufYeafiFC0ImTLcpEjBvCTW
UoAniBSVx1PHK4IAUb3pMdPtIv1uBlIMotHS/GdEyHU6qOsX5ijHqncHHneaytmL
+wJukPqASEBl3F2UnzryBUgGqr1wyH9vtPGjklnngQKBgQDZv3oxZWul//2LV+jo
ZipbnP6nwG3J6pOWPDD3dHoZ6Q2DRyJXN5ty40PS393GVvrSJSdRGeD9+ox5sFoj
iUMgd6kHG4ME7Fre57zUkqy1Ln1K1fkP5tBUD0hviigHBWih2/Nyl2vrdvX5Wpxx
5r42UQa9nOzrNB03DTOhDrUszQKBgQDB+xdMRNSFfCatQj+y2KehcH9kaANPvT0l
l9vgb72qks01h05GSPBZnT1qfndh/Myno9KuVPhJ0HrVwRAjZTd4T69fAH3imW+R
7HP+RgDen4SRTxj6UTJh2KZ8fdPeCby1xTwxYNjq8HqpiO6FHZpE+l4FE8FalZK+
Z3GhE7DuuQKBgDq7b+0U6xVKWAwWuSa+L9yoGvQKblKRKB/Uumx0iV6lwtRPAo89
23sAm9GsOnh+C4dVKCay8UHwK6XDEH0XT/jY7cmR/SP90IDhRsibi2QPVxIxZs2I
N1cFDEexnxxNtCw8VIzrFNvdKXmJnDsIvvONpWDNjAXg96RatjtR6UJdAoGBAIAx
HU5r1j54s16gf1QD1ZPcsnN6QWX622PynX4OmjsVVMPhLRtJrHysax/rf52j4OOQ
YfSPdp3hRqvoMHATvbqmfnC79HVBjPfUWTtaq8xzgro8mXcjHbaH5E41IUSFDs7Z
D1Raej+YuJc9RNN3orGe+29DhO4GFrn5xp/6UV0RAoGBAKUdRgryWzaN4auzWaRD
lxoMhlwQdCXzBI1YLH2QUL8elJOHMNfmja5G9iW07ZrhhvQBGNDXFbFrX4hI3c/0
JC3SPhaaedIjOe9Qd3tn5KgYxbBnWnCTt0kxgro+OM3ORgJseSWbKdRrjOkUxkab
/NDvel7IF63U4UEkrVVt1bYg
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIIDmDCCAoACAQEwDQYJKoZIhvcNAQELBQAwgZExCzAJBgNVBAYTAkNOMREwDwYD
VQQIDAhTaGFuZ2hhaTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtw
bGF5MQwwCgYDVQQLDANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAe
BgkqhkiG9w0BCQEWEW1haWxAbGlua3BsYXkuY29tMB4XDTE4MTExNTAzMzI1OVoX
DTQ2MDQwMTAzMzI1OVowgZExCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhTaGFuZ2hh
aTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtwbGF5MQwwCgYDVQQL
DANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAeBgkqhkiG9w0BCQEW
EW1haWxAbGlua3BsYXkuY29tMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEApP7trR9C8Ajr/CZqi70HYzQHZMX0gj8K3RzO0k5aucWiRkHtvcnfJIz+4dMB
EZHjv/STutsFBwbtD1iLEv48Cxvht6AFPuwTX45gYQ18hyEUC8wFhG7cW7Ek5HtZ
aLH75UFxrpl6zKn/Vy3SGL2wOd5qfBiJkGyZGgg78JxHVBZLidFuU6H6+fIyanwr
ejj8B5pz+KAui6T7SWA8u69UPbC4AmBLQxMPzIX/pirgtKZ7LedntanHlY7wrlAa
HroZOpKZxG6UnRCmw23RPHD6FUZq49f/zyxTFbTQe5NmjzG9wnKCf3R8Wgl8JPW9
4yAbOgslosTfdgrmjkPfFIP2JQIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQARmy6f
esrifhW5NM9i3xsEVp945iSXhqHgrtIROgrC7F1EIAyoIiBdaOvitZVtsYc7Ivys
QtyVmEGscyjuYTdfigvwTVVj2oCeFv1Xjf+t/kSuk6X3XYzaxPPnFG4nAe2VwghE
rbZG0K5l8iXM7Lm+ZdqQaAYVWsQDBG8lbczgkB9q5ed4zbDPf6Fsrsynxji/+xa4
9ARfyHlkCDBThGNnnl+QITtfOWxm/+eReILUQjhwX+UwbY07q/nUxLlK6yrzyjnn
wi2B2GovofQ/4icVZ3ecTqYK3q9gEtJi72V+dVHM9kSA4Upy28Y0U1v56uoqeWQ6
uc2m8y8O/hXPSfKd
-----END CERTIFICATE-----"""

# Status field mapping for parser
# Maps API response keys to model field names
STATUS_MAP: dict[str, str] = {
    "status": "play_status",
    "state": "play_status",
    "player_state": "play_status",
    "vol": "volume",
    "mute": "mute",
    "eq": "eq_preset",
    "EQ": "eq_preset",
    "eq_mode": "eq_preset",
    "loop": "loop_mode",
    "curpos": "position_ms",
    "totlen": "duration_ms",
    "Title": "title_hex",
    "Artist": "artist_hex",
    "Album": "album_hex",
    "DeviceName": "device_name",
    "uuid": "uuid",
    "ssid": "ssid",
    "MAC": "mac_address",
    "firmware": "firmware",
    "project": "project",
    "WifiChannel": "wifi_channel",
    "RSSI": "wifi_rssi",
}

# Mode value mapping
# Maps numeric mode values to source names
MODE_MAP: dict[str, str] = {
    "0": "idle",
    "1": "airplay",
    "2": "dlna",
    "3": "wifi",
    "4": "line_in",
    "5": "bluetooth",
    "6": "optical",
    "10": "wifi",
    "11": "usb",
    "20": "wifi",
    "31": "spotify",
    "34": "lyrion",  # Lyrion Music Server / LMS (Squeezelite) - Issue mjcumming/wiim#188
    "36": "qobuz",
    "40": "line_in",
    "41": "bluetooth",
    "43": "optical",
    "44": "rca",  # Audio Pro RCA line input (confirmed via tcpdump on Link 2)
    "47": "line_in_2",
    "49": "hdmi",
    "51": "usb",
    "60": "line_in",
    "99": "follower",
}

# Sentinel value for entity_picture when using embedded fallback logo
# This tells HA there's cover art to fetch, and tells fetch_cover_art() to serve embedded logo
DEFAULT_WIIM_LOGO_URL = "pywiim:embedded-logo"

# Embedded PyWiim square logo (PNG format) - used as fallback when no cover art is available
# Size: 4965 bytes (4.85 KB) - Square icon from mjcumming/wiim integration
# Dimensions: 256x257 (basically square for UI purposes)
# This is returned directly as bytes when fetch_cover_art() is called with embedded logo sentinel
# No URL fetching needed - just decode base64 and serve the embedded image
EMBEDDED_LOGO_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAQAAAAEBCAYAAACXLnvDAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAAXNS"
    "R0IArs4c6QAAAARnQU1BAACxjwv8YQUAABL6SURBVHgB7d1LbFxVnsfxUy7yQMSOWfOYsBsB0qTFAsgG"
    "ZwFkVgMSII1YkCEgDatOYE8cFoxmAcksWEHALRYjHlLDioQscDY8NhCkALPDw0PqFot2EkdK4jju8yvV"
    "SReVetxz6tZ9/b8fybFjV/n6Vt3zu+d1z3UOgFktV1Hz3sbGxsK1a9f+aWZmZre+1Wq19Nltbm7uckDF"
    "+ONzxX9a9cenPs74jxX/vW9vuummM6ueq6DKBIAK/Pr6+jMq7P5FW6CQo2FW/McZf0L7yJ/YTl+6dGnF"
    "VUCpAaBC71+Qg76wP+T/u+AAI/xJ7owPgiX/8XGZYVBKAMzOzj7mP/3RUegBWfYnwqWLFy/+yRWssADo"
    "Odur4M87AP1WfBlZLDIIph4AFHwgWmFBMNUA2LFjx4Lv1HuHDj0gydSDYCoB4E/6u3znxjuONj6QhyU/"
    "QnZkGp2FbZezubm5gz61/td/+c8OQB52t9vt/Vu2bPmLD4JvXY5yqwF02/rHfHX/GQdgWpZ8GBzKa2JR"
    "LgGgKr8v/J/R1gcKseJrAnvzaBLMuAmpo8+397+h8AOF2eWbA9+o7LkJTdQHMDs7u7/Vav3Zf7ndASjS"
    "dl/29m/fvv3c5cuXv3SJkgPAd/Yt+k9HHYAy7fMh0PIhsOwSJAWACr+v8h92AKpgITUEogNAw3y+8P+X"
    "A1AlC75fYCV2mDBqFECdDr7d8ZkDUEn+5Lx3bW1tOevjMwdAd3bfN475/ECVrfpawB+yDhFmCoDuJB+G"
    "+oB6WGm323/IMlko0zwAf+Y/SuEHakO19UwjdGM7ATXW7z8tOgB1sjvLHIGRTQCm+AK1NrY/YGQTwFcj"
    "DlP4gdqa90OD74x6wNAA6Fb99zsAdbYw6pqBoU2Aubm5Hzn7A42wcuHChbsG/WBgJyBnf6BR5rdu3equ"
    "XLlyuv8HA2sAnP2Bxlltt9t39c8NuKEPQGd/Cj/QOPNXr179Y/83b6gBcPYHGmvV9wXc2vuN39UAOPsD"
    "jTbfPyLQ3wRgQU+gwVqt1u/W8bjeBOhe7fejA9BovjPw1tAZeL0G4Av/ggPQeOvr69dr+r1NAKr/gAEz"
    "MzOPha87TQCq/4AtoRnQqQFQ/Qds8c2Af9Pn0AR4yAGwZEH/dALADw3sdgDM8P0AC/rc0np/vgnwNwfA"
    "FPUDzFy9epWzP2CQyv7M5ubmvzgA5qjsz/j2/y4HwByVfQIAMKoTAI47/QAm6cpfagCAUb7sz6sTkBoA"
    "YNM8TQDArvlM9wYE0EwEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEE"
    "AGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEE"
    "AGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEEAGAYAQAYRgAAhhEAgGEE"
    "AGAYAQAYRgAAhpUWAHNzc+6ll15yX331lfv11187H59++ql77rnn3O233+7q7sEHH3SLi4vX9++HH35w"
    "x48fd48++qjLyx133PG7bYTX8Mknn3R50r58+OGHnX3o3Rd9Py/aFx0P+vu1P/rQNvLel7Lofe99DbWf"
    "R48eLf1Yb83Ozm66gj311FPuyJEjnRAY5Oeff3YHDhxw3333nasjHcgvvvji0J+///777vDhw+78+fMu"
    "1fPPP9/ZxqjX8IknnnC//PKLS6Xf/corr4wshG+99VZnXyYxbl+++OILd/DgwYn2pSwKNhX0UWGp10+v"
    "YxkKDwAl4dtvvz32cSocOoDrFgLjCn+gg1r7l0IBqoNqnElDQO9TlhqLAu3QoUMuRdbXK49AK9o999zT"
    "eQ2znOXLCoFCA0BpqGpQ1mqP3vQHHnjA1UWoKmeV8qbHvoYnTpzo1KZiZQ2ZQIVToRZD+/Lll19mfnyd"
    "Tgoq/HqfhtVq+mnf7r///olqhSkK7QNQAYlp8+gAybPNPG06m8VQf0es2Ndw3759mQ/CXrF/W+y+S5Yz"
    "fy/txzT6OPKm8Iwp/KLH6nlFKzQAUgpznQIgtlNMARdbOIt4DfU36QwWI/bxonBKcezYsaTAKYL6M1Rz"
    "Sgnd1NdjEoUGgA74WDt37nR1kLJvEnugpLwesc9J2Yb2I7ZHO6WQBKo9VC0E9PdoVCZVSohOqtAASD2w"
    "8A/nzp1zsVKek6LoDjqFgEaTqiBrZ+YoZRzrTASqmZQOsO+//z7q8ep8je2MKqtjTn0Vmi9Q5olCITRp"
    "4S8LAVAzH3zwQdTjVZhTCuebb7451cfnSW3n2E63PGh76o9I6cytCgKgZlSgY4YOU+caaBtZq/T6m2KD"
    "KW9qP2uEoKiZdSr8Cp26z1QkAGpI8weyFLhJZs+FMfdxzw8TdKogdo7EJNs5depUKZ12eSMAakqFW7Pv"
    "BhXQzz//3D3yyCMTn5VD4dZMv34KiNdee62znSrNzpt2CBQVMkUpdCagLvCIfeF0MNehmhU7qy3Q7K9J"
    "C5DORKH9q/b+tGaThXkO+v0pHYX9dFHMtExj1mDM1N5Ut912myvSTQ61V1QPfOxU3zKFWYOqKeXRPxE7"
    "tbcuaAKg0fLopdcUXYVJE+ekEABoPI3Tp84aDFN7m4omAEwIE3XUcZlVHrP7qo4AaAC1T/WhKb/qUJxG"
    "n4Cqv+oE1HRubUfbqNsCHWHRkSwLmFgo/EIA1NiwlXTUQ68zXR6dX/rd2o7a0f3b0fCgtpNXEChUNOoT"
    "fl8InT179ri8hCXnNIQ6bBRD/QZ5jjxpO5988klnSra+Dldbar/KHk4kAGpKPdLDLj/WkKQO4jvvvDOq"
    "yjvo94wa81bnmP6GSZdvO3nyZGcq8bBRBv0dKpAKojw64jR1WL9Tw4S9IZBlCbQYCmIFzajRE72Gqm2U"
    "FQTMA8hJkfMA1KmVtWf72Wef7RSwFFnfLx3omhAUOy9AC2S+/PLLnZpKWBAjNDPk7NmznZ+FcMl7Ek7v"
    "MmNham9es/sUaK+//vr110S/V8Fz9913d/ZP29axHWpp4fLmoucBEAA5KSoAYreTuqxabBtYNQ0d8DF0"
    "LGjfxy0K2r+IakwAjhPO0vqdeRX+/tdi1N/buwCuHlP0uoAMA9ZM7IGvwEhZvjt2eaqU5axC4dciGqOq"
    "9v1LbCkMJmna9Aq1imkV/nHzELR9zTHQe1TGoqAEQM2kHKgpS5XF1tRSljcL9zXIQvvdW5BUyPIKgbxo"
    "1mFv4VctKmvtNXUZsUkRAAYUeYlsjNjaTH8noArbqN78ooTrDvpHXWJqRQrDMtYVIABQmtiaSRgW7KX+"
    "gf7e/CKFjsT+nv7Y1Zslz+HOrEwNA+pNCdXbMJGlrncfaoKU5sygWobeQ41CFH2Z7qiblaQsEpvnrday"
    "MhEAWhZb47uDDo48J82gPKEwFhUC07pTURgZKUrjmwAaghl1DXeYNFPVdeaRXSiU067VhRpHHe9V2K/R"
    "ARBzKWiVlphGumFt8ryU3eeQt8YGQMp87iosMY3JDeuVn1S4CWpTCr80LgBUeFXlT509GJaYbsqab5Zp"
    "XD6vuQL6Pal3QK6yRgVAmM896f0Ew/JPhED95TFhKGWac100JgDyntLZtNVfLZskBJpc+KURAZB34Z/2"
    "70XxVIizLATSq39qbxPVPgCKWge+Trcpx2C62EaXR48bvptWJ2IV1ToAirod1KQdi6gOrY2gwq2qff98"
    "AV16ru/rEu06LYE+iUJnAmotubwKq6ZNqlAWOWSXxyo7KJ/mCqhqH6r3Rc++q5JCawApqTpoVlf/9eFF"
    "Ciu39NNBlcLqgVcllt+DQgPgxIkTLlb/clYqfGWv0z4sBGIDTlVOoEyF1wBiConOqr2Pr9JSzYNCILZp"
    "0PQeZlRf4Z2Aw+5o26//ttNqf+dV+POaytkfAgqrrCGgx1npaEJ1FRoAartnuYxSVePe1Vrz7IEPvbyp"
    "K+X2Uwj0NkmyTDrReLSGmJp8yynUQ6EBoLOlhu02Nzc7hVBjsrrAQgVeH++9916n4Kuwq/Crp//UqVO5"
    "jcGr4IWlmrXtvBZhVLBppd4wwqFtaCVeLQ2tTkyFnj7r/9pvfc0sQ1RB4QuCaOxey4Or4KsADrrAQgVf"
    "YZHXCikq8JrV1X/WVyBoaDKPtQA0YSjslz5Uve9f8FL7o4VJQqD99NNPDihTaSsC6aypDxXOMNSn6n7K"
    "6rKjhFldwxaJCB1xeS0IEvZLtE1tP+wTlxmjakpfEmzQQo95ybpsk0JAj9GCIHkWUq4hQNU1dkGQ2DXb"
    "wkovTMyBJY0MAFW9Uwpz6vOAumpcAExaiKe12itQRY0KAFXjU+5S26+o1WWBsjUmADTGnueabdNeXRao"
    "gkYEgGbeZb3JZAxLC0PAptoHQBFrtuW5uixQJbW+NZgKZlFn57wnDAFVUMsaQJjaW3TVvIr3pAcmUbsa"
    "wLipvdMWLibiNmJoglrVANQz//DDD5c+PBcuYmrSLaJgU6EBoCvvUlVtgk6dbhJJUNVH0e9VoQGQeuau"
    "6uy8SW8TnfK8lBCNfd1Tgzp2f1L2vy4zNFNeQx3njQ4AnTVjVf1e7JOEU8qioCkTk2Kfo4OwiAVOUxaJ"
    "rcvszCLepzwUvihoTEGpSzU7JQT0nJRRDL0mMdtRIUsJp9jRjpRwj12RSbM969Kc0d8Z+5qUMcJUeCeg"
    "luLK8iaGqb11ecNjrh8IIxkpwhBo1r8p9n54QewCpylhFvP36XWt2yrK2res4Rvz2Dy1t23btugK9Ntv"
    "v7nl5WW3d+/egYtv6KBQwT9+/LirGxXOd999t/P1nj17Bj5GVeWnn356ojdbz1WBuO+++4YuYKKfT7qd"
    "UCUdti/a31dffdW98cYbLtXXX389chuipdyynjiq5PLly52/fd++fUPfJ+3TCy+8UNp089bs7OymK4mW"
    "zgrr46ng68VqysU3WgZMKwZrVSC9+Sr4epPz3D9tQ6spaRHVnTt3dr539uzZqWynd1/C/RpUhc+rUGob"
    "Bw4c6ASBtqNtqPnSlGNCx7rep3vvvbfzf71P2jc1E8oMtlIDAEC5GrskGIDxCADAMAIAMIwAAAwjAADD"
    "CADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADD"
    "CADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADD"
    "CADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAwjAADDCADAMAIAMIwAAAxTAKw6ABatzrRaLQIAsGmVGgBg"
    "1Obm5sqM/nEAzFHtnwAAjKIGABjWCQBfDfjWATDHl/0zrXlvY2Pjbw6AKe12+9aZVc8nwYoDYIav/p9R"
    "2e/MBLx27dpHDoAZqv7r80z3P/QDALZ0TvqdAPBtAWoAgCHr6+udk34nANQW8J+WHYDG8+3/5UuXLq3o"
    "6+tXA9IPANjgA2ApfH09ALZs2fInB6Dx/LD/6fD19QCgGQCY8FGo/svvFgTxVYMjDkCTLfX+p9X/07m5"
    "uR99EOxyAJpm5cKFC3f1fuOGJcF8++CYA9A4vqN/sf97N9QAdG2Af+A31AKARrnh7C/t/m/4DoJLW7du"
    "Pee/fMwBaAR/Uj8YJv/0ag17gu8LUC1gtwNQdwPP/jJ0WXCfGIccgCY4OOwHQwNgbW1t2XUvGABQW0v+"
    "7P/xsB+2Rj2zu1jIj/rSAaibFd/u39s78affyDsDdWcH/ocDUDsa9htV+KXtxrhy5cr/+VGB+Var9YAD"
    "UAu+A//YxYsX/3vc41oug+7cgM8YFQBqYWivf79MNwftrB02M/M4awcClddp92d9cKYaQHDLLbfs9kHw"
    "maNTEKiiVV9T3+ur/meyPmFsH0Avnyx/2bZt218dswSByvGF/z994T8Z85yoABDfKXjGh8D/O0IAqAxf"
    "+Pf7wh+9qE90AAghAFRHauGXpACQbgjo4oJ9/mO7A1C01W61P3k5v6hOwEHUMdhut//M5cNAoVZ84X88"
    "psNvkIkDQObn53d15wnscgCmSnf18TXwx8fN8ssi0zyAcVZXV1fOnz9/l2YfOQBTozLmh+L35lH4JbkP"
    "YBCfSifVOegTSjMGmSsA5EfX5fz72tra/2jRHpeTXANA1Dl48803f+yTSgHA1GFgcku+n+1ffS17ovb+"
    "ILn0AQyzY8eOh3x1ZYm+ASCebuHlPy36s/5pNyVTDYBgdnZ2v28WHCYIgEzUw784yfBeVoUEQEAQAMPp"
    "jK/79hVR8INCAyBQ08AHwX7/5X4HGFdEVX+YUgIg0PyBjY2NBf8CPOMDYcEBRnTP9h/pprzdlbdKUWoA"
    "9OquP/iQf1EW/H8XukOJQCP441o9+Mv+uF72Pfqnyyz0vSoTAIN0mwrzWolIgdAdWtTyZJ3PjrkGqIbV"
    "7ocK+oo+/DG6qhl7vjPvW3+WX6lKge/3dzsDuj9yP4mqAAAAAElFTkSuQmCC"
)

# EQ preset numeric mapping
# Maps numeric EQ preset values to preset names
# EQ Preset names
EQ_PRESET_OFF = "off"  # Special value: EQ is disabled (not a preset, but used in sound_mode)
EQ_PRESET_FLAT = "flat"
EQ_PRESET_ACOUSTIC = "acoustic"
EQ_PRESET_BASS = "bass"
EQ_PRESET_BASSBOOST = "bassboost"
EQ_PRESET_BASSREDUCER = "bassreducer"
EQ_PRESET_CLASSICAL = "classical"
EQ_PRESET_DANCE = "dance"
EQ_PRESET_DEEP = "deep"
EQ_PRESET_ELECTRONIC = "electronic"
EQ_PRESET_HIPHOP = "hiphop"
EQ_PRESET_JAZZ = "jazz"
EQ_PRESET_LOUDNESS = "loudness"
EQ_PRESET_POP = "pop"
EQ_PRESET_ROCK = "rock"
EQ_PRESET_TREBLE = "treble"
EQ_PRESET_VOCAL = "vocal"
EQ_PRESET_CUSTOM = "custom"

# EQ Preset mapping (preset name -> display name)
# Note: EQ_PRESET_OFF is intentionally NOT in this map - it's handled separately
# as it represents "EQ disabled" rather than an actual EQ preset
EQ_PRESET_MAP: dict[str, str] = {
    EQ_PRESET_FLAT: "Flat",
    EQ_PRESET_ACOUSTIC: "Acoustic",
    EQ_PRESET_BASS: "Bass",
    EQ_PRESET_BASSBOOST: "Bass Booster",
    EQ_PRESET_BASSREDUCER: "Bass Reducer",
    EQ_PRESET_CLASSICAL: "Classical",
    EQ_PRESET_DANCE: "Dance",
    EQ_PRESET_DEEP: "Deep",
    EQ_PRESET_ELECTRONIC: "Electronic",
    EQ_PRESET_HIPHOP: "Hip-Hop",
    EQ_PRESET_JAZZ: "Jazz",
    EQ_PRESET_LOUDNESS: "Loudness",
    EQ_PRESET_POP: "Pop",
    EQ_PRESET_ROCK: "Rock",
    EQ_PRESET_TREBLE: "Treble",
    EQ_PRESET_VOCAL: "Vocal",
    EQ_PRESET_CUSTOM: "Custom",
}

EQ_NUMERIC_MAP: dict[str, str] = {
    "0": "flat",
    "1": "pop",
    "2": "rock",
    "3": "jazz",
    "4": "classical",
    "5": "bass",
    "6": "treble",
    "7": "vocal",
    "8": "loudness",
    "9": "dance",
    "10": "acoustic",
    "11": "electronic",
    "12": "deep",
}

# Vendor identifiers
VENDOR_WIIM = "wiim"
VENDOR_ARYLIC = "arylic"
VENDOR_AUDIO_PRO = "audio_pro"
VENDOR_LINKPLAY_GENERIC = "linkplay_generic"

# Default connection settings
DEFAULT_PORT = 443  # HTTPS port
DEFAULT_TIMEOUT = 5.0  # seconds

# Protocol probe timeout constants
# These timeouts are set to accommodate mTLS handshake requirements for devices
# like Audio Pro Link2 which use port 4443 and require mutual TLS authentication.
# The mTLS exchange can take several seconds to complete, so these values provide
# sufficient headroom for reliable connection establishment.
PROBE_TIMEOUT_CONNECT = 1.0  # Connection timeout for protocol probe (seconds)
PROBE_TIMEOUT_TOTAL = 5.0  # Total timeout for protocol probe (seconds)
PROBE_ASYNC_TIMEOUT = 5.0  # Async operation timeout for protocol probe (seconds)

# Play mode constants
PLAY_MODE_NORMAL = "normal"
PLAY_MODE_REPEAT_ALL = "repeat_all"
PLAY_MODE_REPEAT_ONE = "repeat_one"
PLAY_MODE_SHUFFLE = "shuffle"
PLAY_MODE_SHUFFLE_REPEAT_ALL = "shuffle_repeat_all"

# API endpoint paths
# All endpoints use the /httpapi.asp base path with command parameter
API_ENDPOINT_STATUS = "/httpapi.asp?command=getStatusEx"
API_ENDPOINT_PLAYER_STATUS = "/httpapi.asp?command=getPlayerStatusEx"
API_ENDPOINT_METADATA = "/httpapi.asp?command=getMetaInfo"

# Player control endpoints
API_ENDPOINT_PLAY = "/httpapi.asp?command=setPlayerCmd:play"
API_ENDPOINT_PAUSE = "/httpapi.asp?command=setPlayerCmd:pause"
API_ENDPOINT_STOP = "/httpapi.asp?command=setPlayerCmd:stop"
API_ENDPOINT_NEXT = "/httpapi.asp?command=setPlayerCmd:next"
API_ENDPOINT_PREV = "/httpapi.asp?command=setPlayerCmd:prev"
API_ENDPOINT_VOLUME = "/httpapi.asp?command=setPlayerCmd:vol:"
API_ENDPOINT_MUTE = "/httpapi.asp?command=setPlayerCmd:mute:"
API_ENDPOINT_SEEK = "/httpapi.asp?command=setPlayerCmd:seek:"
API_ENDPOINT_LOOPMODE = "/httpapi.asp?command=setPlayerCmd:loopmode:"
API_ENDPOINT_SOURCE = "/httpapi.asp?command=setPlayerCmd:switchmode:"

# Device info endpoints
API_ENDPOINT_DEVICE_INFO = "/httpapi.asp?command=getDeviceInfo"
API_ENDPOINT_FIRMWARE = "/httpapi.asp?command=getFirmwareVersion"
API_ENDPOINT_DEBUG_INFO = "/httpapi.asp?command=getDebugInfo"

# Multiroom endpoints
API_ENDPOINT_GROUP_SLAVES = "/httpapi.asp?command=multiroom:getSlaveList"
API_ENDPOINT_GROUP_EXIT = "/httpapi.asp?command=multiroom:Ungroup"
API_ENDPOINT_GROUP_KICK = "/httpapi.asp?command=multiroom:SlaveKickout:"
API_ENDPOINT_GROUP_SLAVE_MUTE = "/httpapi.asp?command=multiroom:SlaveMute:"
API_ENDPOINT_GROUP_SLAVE_VOLUME = "/httpapi.asp?command=multiroom:SlaveVolume:"

# EQ endpoints
API_ENDPOINT_EQ_GET = "/httpapi.asp?command=EQGetBand"
API_ENDPOINT_EQ_STATUS = "/httpapi.asp?command=EQGetStat"
API_ENDPOINT_EQ_LIST = "/httpapi.asp?command=EQGetList"
API_ENDPOINT_EQ_PRESET = "/httpapi.asp?command=EQLoad:"
API_ENDPOINT_EQ_CUSTOM = "/httpapi.asp?command=EQSetBand:"
API_ENDPOINT_EQ_ON = "/httpapi.asp?command=EQOn"
API_ENDPOINT_EQ_OFF = "/httpapi.asp?command=EQOff"

# Preset endpoints
API_ENDPOINT_PRESET_INFO = "/httpapi.asp?command=getPresetInfo"
API_ENDPOINT_PRESET = "/httpapi.asp?command=MCUKeyShortClick:"

# Device info endpoints
API_ENDPOINT_MAC = "/httpapi.asp?command=getMAC"

# Playback control endpoints
API_ENDPOINT_RESUME = "/httpapi.asp?command=setPlayerCmd:resume"
API_ENDPOINT_CLEAR_PLAYLIST = "/httpapi.asp?command=setPlayerCmd:clear_playlist"
API_ENDPOINT_PLAY_URL = "/httpapi.asp?command=setPlayerCmd:play:"
API_ENDPOINT_PLAY_M3U = "/httpapi.asp?command=setPlayerCmd:playlist:"
API_ENDPOINT_PLAY_PROMPT_URL = "/httpapi.asp?command=setPlayerCmd:playPromptUrl:"

# Audio settings endpoints
API_ENDPOINT_GET_SPDIF_SAMPLE_RATE = "/httpapi.asp?command=getSpdifOutSampleRate"
API_ENDPOINT_SET_SPDIF_SWITCH_DELAY = "/httpapi.asp?command=setSpdifOutSwitchDelayMs:"
API_ENDPOINT_GET_CHANNEL_BALANCE = "/httpapi.asp?command=getChannelBalance"
API_ENDPOINT_SET_CHANNEL_BALANCE = "/httpapi.asp?command=setChannelBalance:"
API_ENDPOINT_GET_SOUND_CARD_MODE_SUPPORT_LIST = "/httpapi.asp?command=getSoundCardModeSupportList"

# Miscellaneous endpoints
API_ENDPOINT_SET_LED = "/httpapi.asp?command=LED_SWITCH_SET:"
# Read-only status LED state (plain text 0|1 on many WiiM devices; safe at connect — no mutation)
API_ENDPOINT_GET_LED_SWITCH = "/httpapi.asp?command=LED_SWITCH_GET"
# Arylic: query LED state via MCU ASCII (getMCUASCIICmd:LED); may not be on all devices
API_ENDPOINT_GET_LED_MCU = "/httpapi.asp?command=getMCUASCIICmd:LED"
API_ENDPOINT_SET_BUTTONS = "/httpapi.asp?command=Button_Enable_SET:"
# WiiM Ultra display/LCD (setLightOperationBrightConfig) - screen on/off and brightness
# Single JSON command (not the same as LED_SWITCH_SET / setLED). Payload always includes
# default_bright; 1 is minimum on-device (see mjcumming/wiim#213).
API_ENDPOINT_DISPLAY_CONFIG = "/httpapi.asp?command=setLightOperationBrightConfig:"
DISPLAY_BRIGHTNESS_MIN = 1
DISPLAY_BRIGHTNESS_MAX = 100
DISPLAY_DEFAULT_BRIGHTNESS = 100
API_ENDPOINT_GET_AUDIO_INPUT_ENABLE = "/httpapi.asp?command=getAudioInputEnable"
API_ENDPOINT_GET_AUDIO_INPUT_CAPABILITY = "/httpapi.asp?command=getAudioInputCapbility"
API_ENDPOINT_GET_MODE_RENAME = "/httpapi.asp?command=getModeRename"
API_ENDPOINT_GET_ACOUSTIC_CAPABILITY = "/httpapi.asp?command=GetAcousticCapability"
API_ENDPOINT_GET_ALL_ROUTINES = "/httpapi.asp?command=getAllRoutines"

# Bluetooth endpoints
API_ENDPOINT_START_BT_DISCOVERY = "/httpapi.asp?command=startbtdiscovery:"
API_ENDPOINT_GET_BT_DISCOVERY_RESULT = "/httpapi.asp?command=getbtdiscoveryresult"
API_ENDPOINT_CONNECT_BT_A2DP = "/httpapi.asp?command=connectbta2dpsynk:"
API_ENDPOINT_DISCONNECT_BT_A2DP = "/httpapi.asp?command=disconnectbta2dpsynk"
API_ENDPOINT_GET_BT_PAIR_STATUS = "/httpapi.asp?command=getbtpairstatus"
API_ENDPOINT_GET_BT_HISTORY = "/httpapi.asp?command=getbthistory"
API_ENDPOINT_CLEAR_BT_DISCOVERY = "/httpapi.asp?command=clearbtdiscoveryresult"

# LMS/Squeezelite endpoints
API_ENDPOINT_SQUEEZELITE_STATE = "/httpapi.asp?command=Squeezelite:getState"
API_ENDPOINT_SQUEEZELITE_DISCOVER = "/httpapi.asp?command=Squeezelite:discover"
API_ENDPOINT_SQUEEZELITE_AUTO_CONNECT = "/httpapi.asp?command=Squeezelite:autoConnectEnable:"
API_ENDPOINT_SQUEEZELITE_CONNECT_SERVER = "/httpapi.asp?command=Squeezelite:connectServer:"

# Audio output endpoints
API_ENDPOINT_AUDIO_OUTPUT_STATUS = "/httpapi.asp?command=getNewAudioOutputHardwareMode"
API_ENDPOINT_AUDIO_OUTPUT_SET = "/httpapi.asp?command=setAudioOutputHardwareMode:"

# Timer and alarm endpoints (WiiM devices only)
API_ENDPOINT_SET_ALARM = "/httpapi.asp?command=setAlarmClock:"
API_ENDPOINT_GET_ALARM = "/httpapi.asp?command=getAlarmClock:"
API_ENDPOINT_ALARM_STOP = "/httpapi.asp?command=alarmStop"
API_ENDPOINT_TIME_SYNC = "/httpapi.asp?command=timeSync:"
API_ENDPOINT_SET_SHUTDOWN = "/httpapi.asp?command=setShutdown:"
API_ENDPOINT_GET_SHUTDOWN = "/httpapi.asp?command=getShutdown"

# Subwoofer control endpoints (WiiM Ultra, firmware 5.2+)
# Undocumented API - discovered via reverse engineering (Issue #2)
API_ENDPOINT_SUBWOOFER_STATUS = "/httpapi.asp?command=getSubLPF"
API_ENDPOINT_SUBWOOFER_SET = "/httpapi.asp?command=setSubLPF:"

# 12V trigger control endpoints (WiiM Ultra / Pro / Pro Plus)
# getTriggeroutStatus → {"status":0|1}, setTriggeroutStatus:0|1 → {"status":"OK"}
# See: https://github.com/mjcumming/pywiim/issues/13
API_ENDPOINT_TRIGGER_OUT_STATUS = "/httpapi.asp?command=getTriggeroutStatus"
API_ENDPOINT_TRIGGER_OUT_SET = "/httpapi.asp?command=setTriggeroutStatus:"

# PEQ / GEQ endpoints - official WiiM LV2 EQ API
# pluginURI (implemented in pywiim): http://moddevices.com/plugins/caps/EqNp
# graphic 10-band pluginURI: http://moddevices.com/plugins/caps/Eq10HP
API_ENDPOINT_PEQ_GET_BAND = "/httpapi.asp?command=EQGetLV2BandEx:"
API_ENDPOINT_PEQ_GET_SOURCE_BAND = "/httpapi.asp?command=EQGetLV2SourceBandEx:"
API_ENDPOINT_PEQ_SET_BAND = "/httpapi.asp?command=EQSetLV2Band:"
API_ENDPOINT_PEQ_SET_SOURCE_BAND = "/httpapi.asp?command=EQSetLV2SourceBand:"
API_ENDPOINT_PEQ_CHANGE_FX = "/httpapi.asp?command=EQChangeFX:"
API_ENDPOINT_PEQ_CHANGE_SOURCE_FX = "/httpapi.asp?command=EQChangeSourceFX:"
API_ENDPOINT_PEQ_SOURCE_OFF = "/httpapi.asp?command=EQSourceOff:"
API_ENDPOINT_PEQ_GET_LIST = "/httpapi.asp?command=EQv2GetList:"
API_ENDPOINT_PEQ_GET_NEW_LIST = "/httpapi.asp?command=EQv2GetNewList:"
API_ENDPOINT_PEQ_SAVE = "/httpapi.asp?command=EQSave:"
API_ENDPOINT_PEQ_SOURCE_SAVE = "/httpapi.asp?command=EQSourceSave:"
API_ENDPOINT_PEQ_LOAD = "/httpapi.asp?command=EQv2Load:"
API_ENDPOINT_PEQ_SOURCE_LOAD = "/httpapi.asp?command=EQv2SourceLoad:"
API_ENDPOINT_PEQ_DELETE = "/httpapi.asp?command=EQv2Delete:"
API_ENDPOINT_PEQ_RENAME = "/httpapi.asp?command=EQv2Rename:"
API_ENDPOINT_PEQ_SET_CHANNEL_MODE = "/httpapi.asp?command=EQSetChannelMode:"

# PEQ plugin URI (Parametric Equalizer)
PEQ_PLUGIN_URI = "http://moddevices.com/plugins/caps/EqNp"

# GEQ plugin URI (Graphic 10-band Equalizer)
GEQ_PLUGIN_URI = "http://moddevices.com/plugins/caps/Eq10HP"

# Room correction read endpoint. Uses the PEQ-shaped EqNp LV2 payload, but it is
# a distinct device-side correction block rather than the user PEQ preset.
API_ENDPOINT_ROOM_CORRECTION_GET = "/httpapi.asp?command=RoomCorrGet"

# PEQ band letters (10 active bands: a-j; k-l exist but default to Off)
PEQ_BAND_LETTERS = ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j")

# PEQ default frequencies by band letter (1-octave spacing)
PEQ_DEFAULT_FREQUENCIES: dict[str, float] = {
    "a": 31.25,
    "b": 62.5,
    "c": 125.0,
    "d": 250.0,
    "e": 500.0,
    "f": 1000.0,
    "g": 2000.0,
    "h": 4000.0,
    "i": 8000.0,
    "j": 16000.0,
}

# PEQ filter mode values
PEQ_MODE_OFF = -1
PEQ_MODE_LOW_SHELF = 0
PEQ_MODE_PEAK = 1
PEQ_MODE_HIGH_SHELF = 2

# PEQ parameter ranges
PEQ_FREQ_MIN = 10.0
PEQ_FREQ_MAX = 22000.0
PEQ_Q_MIN = 0.01
PEQ_Q_MAX = 24.0
PEQ_GAIN_MIN = -12.0
PEQ_GAIN_MAX = 12.0

# PEQ parameter defaults
PEQ_DEFAULT_MODE = PEQ_MODE_PEAK
PEQ_DEFAULT_Q = 0.25
PEQ_DEFAULT_GAIN = 0.0

# PEQ channel mode values
PEQ_CHANNEL_MODE_STEREO = "Stereo"
PEQ_CHANNEL_MODE_LR = "L/R"

# Subwoofer setting constants
SUBWOOFER_CROSSOVER_MIN = 30
SUBWOOFER_CROSSOVER_MAX = 250
SUBWOOFER_LEVEL_MIN = -15
SUBWOOFER_LEVEL_MAX = 15
SUBWOOFER_DELAY_MIN = -200
SUBWOOFER_DELAY_MAX = 200
SUBWOOFER_PHASE_0 = 0
SUBWOOFER_PHASE_180 = 180

# Audio output mode constants
# Based on real-world device testing (Issue #160) and official WiiM API documentation:
# hardware field values: 1=SPDIF, 2=AUX, 3=COAX, 4=varies by device, 7=HDMI (WiiM Amp Ultra), 8=USB
# source field: 0=BT disabled, 1=BT active (Bluetooth output uses source field)
# audiocast field: 0=DLNA disabled, 1=DLNA active
# NOTE: Mode 0 exists in practice but not documented in official API
# NOTE: WiiM Ultra mode 4: source=0 = Headphone Out, source=1 = Bluetooth Out (Issue #86)
# NOTE: WiiM Amp Ultra mode 7: HDMI ARC output (Issue #122)
# NOTE: USB Out is mode 8 (confirmed on WiiM Ultra, Issue #160). Mode 6 was incorrectly
#        documented in the WiiM API spec; modes 5-7 all revert to mode 4 on Ultra.
AUDIO_OUTPUT_MODE_LINE_OUT = 0  # Undocumented but works on WiiM devices
AUDIO_OUTPUT_MODE_SPDIF_OUT = 1  # AUDIO_OUTPUT_SPDIF_MODE (Optical/TOSLINK)
AUDIO_OUTPUT_MODE_AUX_OUT = 2  # AUDIO_OUTPUT_AUX_MODE (Line Out/Auxiliary/RCA)
AUDIO_OUTPUT_MODE_COAX_OUT = 3  # AUDIO_OUTPUT_COAX_MODE (Coaxial)
AUDIO_OUTPUT_MODE_BLUETOOTH_OUT = 4  # Bluetooth Out (or Headphone Out on Ultra with source=0)
AUDIO_OUTPUT_MODE_HDMI_OUT = 7  # HDMI ARC output (WiiM Amp Ultra)
AUDIO_OUTPUT_MODE_USB_OUT = 8  # USB Out (confirmed on WiiM Ultra, Issue #160)

# Legacy aliases for backward compatibility
AUDIO_OUTPUT_MODE_OPTICAL_OUT = AUDIO_OUTPUT_MODE_SPDIF_OUT
AUDIO_OUTPUT_MODE_LINE_OUT_2 = AUDIO_OUTPUT_MODE_AUX_OUT

# Audio output mode mapping (mode integer -> friendly name)
# Note: Mode 4 defaults to "Bluetooth Out" but is context-dependent on Ultra devices
# (see audio_output_mode property for special Ultra handling)
AUDIO_OUTPUT_MODE_MAP: dict[int, str] = {
    AUDIO_OUTPUT_MODE_LINE_OUT: "Line Out",  # Mode 0 - undocumented
    AUDIO_OUTPUT_MODE_SPDIF_OUT: "Optical Out",  # Mode 1 - SPDIF
    AUDIO_OUTPUT_MODE_AUX_OUT: "Line Out",  # Mode 2 - AUX (primary line out)
    AUDIO_OUTPUT_MODE_COAX_OUT: "Coax Out",  # Mode 3 - COAX
    AUDIO_OUTPUT_MODE_BLUETOOTH_OUT: "Bluetooth Out",  # Mode 4 - default mapping
    6: "USB Out",  # Mode 6 - legacy/doc mapping (kept for backward compat reading)
    AUDIO_OUTPUT_MODE_HDMI_OUT: "HDMI Out",  # Mode 7 - HDMI ARC (WiiM Amp Ultra)
    AUDIO_OUTPUT_MODE_USB_OUT: "USB Out",  # Mode 8 - USB (confirmed on WiiM Ultra, Issue #160)
}

# Reverse mapping (friendly name -> mode integer)
# Maps to mode 2 (AUX) as primary line out per API docs
AUDIO_OUTPUT_MODE_NAME_TO_INT: dict[str, int] = {
    "line out": AUDIO_OUTPUT_MODE_AUX_OUT,  # Map to mode 2 (AUX) per API
    "lineout": AUDIO_OUTPUT_MODE_AUX_OUT,
    "aux": AUDIO_OUTPUT_MODE_AUX_OUT,
    "aux out": AUDIO_OUTPUT_MODE_AUX_OUT,
    "optical out": AUDIO_OUTPUT_MODE_SPDIF_OUT,  # Mode 1 (SPDIF)
    "optical": AUDIO_OUTPUT_MODE_SPDIF_OUT,
    "spdif": AUDIO_OUTPUT_MODE_SPDIF_OUT,
    "spdif out": AUDIO_OUTPUT_MODE_SPDIF_OUT,
    "coax out": AUDIO_OUTPUT_MODE_COAX_OUT,  # Mode 3
    "coax": AUDIO_OUTPUT_MODE_COAX_OUT,
    "coaxial": AUDIO_OUTPUT_MODE_COAX_OUT,
    "headphone out": AUDIO_OUTPUT_MODE_BLUETOOTH_OUT,  # Mode 4 (uses special handling for Ultra)
    "headphone": AUDIO_OUTPUT_MODE_BLUETOOTH_OUT,
    "headphones": AUDIO_OUTPUT_MODE_BLUETOOTH_OUT,
    "bluetooth out": AUDIO_OUTPUT_MODE_BLUETOOTH_OUT,  # Mode 4
    "bluetooth": AUDIO_OUTPUT_MODE_BLUETOOTH_OUT,
    "usb out": AUDIO_OUTPUT_MODE_USB_OUT,  # Mode 8 (confirmed on WiiM Ultra, Issue #160)
    "usb": AUDIO_OUTPUT_MODE_USB_OUT,
    "hdmi out": AUDIO_OUTPUT_MODE_HDMI_OUT,  # Mode 7 (WiiM Amp Ultra)
    "hdmi": AUDIO_OUTPUT_MODE_HDMI_OUT,
    "hdmi arc": AUDIO_OUTPUT_MODE_HDMI_OUT,
}

# Alarm trigger types (WiiM devices only)
ALARM_TRIGGER_CANCEL = 0
ALARM_TRIGGER_ONCE = 1
ALARM_TRIGGER_DAILY = 2
ALARM_TRIGGER_WEEKLY = 3
ALARM_TRIGGER_WEEKLY_BITMASK = 4
ALARM_TRIGGER_MONTHLY = 5

# Alarm operations (WiiM devices only)
ALARM_OP_SHELL = 0
ALARM_OP_PLAYBACK = 1
ALARM_OP_STOP = 2

# LED Control endpoints
API_ENDPOINT_LED = "/httpapi.asp?command=setLED:"
API_ENDPOINT_LED_BRIGHTNESS = "/httpapi.asp?command=setLEDBrightness:"

# Arylic-specific LED commands (experimental - based on user research)
# Arylic devices use different LED command format: MCU+PAS+RAKOIT:LED:
# Documentation: https://github.com/mjcumming/wiim/issues/55
API_ENDPOINT_ARYLIC_LED = "/httpapi.asp?command=MCU+PAS+RAKOIT:LED:"
API_ENDPOINT_ARYLIC_LED_BRIGHTNESS = "/httpapi.asp?command=MCU+PAS+RAKOIT:LEDBRIGHTNESS:"

__all__ = [
    "AUDIO_OUTPUT_MODE_LINE_OUT",
    "AUDIO_OUTPUT_MODE_SPDIF_OUT",
    "AUDIO_OUTPUT_MODE_AUX_OUT",
    "AUDIO_OUTPUT_MODE_OPTICAL_OUT",  # Legacy alias
    "AUDIO_OUTPUT_MODE_LINE_OUT_2",  # Legacy alias
    "AUDIO_OUTPUT_MODE_COAX_OUT",
    "AUDIO_OUTPUT_MODE_BLUETOOTH_OUT",
    "AUDIO_OUTPUT_MODE_USB_OUT",
    "AUDIO_OUTPUT_MODE_HDMI_OUT",
    "AUDIO_OUTPUT_MODE_MAP",
    "AUDIO_OUTPUT_MODE_NAME_TO_INT",
    "WIIM_CA_CERT",
    "AUDIO_PRO_CLIENT_CERT",
    "VENDOR_WIIM",
    "VENDOR_ARYLIC",
    "VENDOR_AUDIO_PRO",
    "VENDOR_LINKPLAY_GENERIC",
    "STATUS_MAP",
    "MODE_MAP",
    "EQ_NUMERIC_MAP",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "API_ENDPOINT_STATUS",
    "API_ENDPOINT_PLAYER_STATUS",
    "API_ENDPOINT_METADATA",
    "API_ENDPOINT_PLAY",
    "API_ENDPOINT_PAUSE",
    "API_ENDPOINT_STOP",
    "API_ENDPOINT_NEXT",
    "API_ENDPOINT_PREV",
    "API_ENDPOINT_VOLUME",
    "API_ENDPOINT_MUTE",
    "API_ENDPOINT_SEEK",
    "API_ENDPOINT_DEVICE_INFO",
    "API_ENDPOINT_FIRMWARE",
    "API_ENDPOINT_DEBUG_INFO",
    "API_ENDPOINT_GROUP_SLAVES",
    "API_ENDPOINT_GROUP_EXIT",
    "API_ENDPOINT_EQ_GET",
    "API_ENDPOINT_EQ_STATUS",
    "API_ENDPOINT_EQ_LIST",
    "API_ENDPOINT_EQ_PRESET",
    "API_ENDPOINT_EQ_CUSTOM",
    "API_ENDPOINT_EQ_ON",
    "API_ENDPOINT_EQ_OFF",
    "API_ENDPOINT_GROUP_KICK",
    "API_ENDPOINT_GROUP_SLAVE_MUTE",
    "API_ENDPOINT_GROUP_SLAVE_VOLUME",
    "EQ_PRESET_MAP",
    "EQ_NUMERIC_MAP",
    "API_ENDPOINT_PRESET_INFO",
    "API_ENDPOINT_PRESET",
    "API_ENDPOINT_AUDIO_OUTPUT_STATUS",
    "API_ENDPOINT_AUDIO_OUTPUT_SET",
    "API_ENDPOINT_GET_SOUND_CARD_MODE_SUPPORT_LIST",
    "API_ENDPOINT_LED",
    "API_ENDPOINT_LED_BRIGHTNESS",
    "API_ENDPOINT_ARYLIC_LED",
    "API_ENDPOINT_ARYLIC_LED_BRIGHTNESS",
    "API_ENDPOINT_DISPLAY_CONFIG",
    "API_ENDPOINT_GET_AUDIO_INPUT_ENABLE",
    "API_ENDPOINT_GET_MODE_RENAME",
    "API_ENDPOINT_GET_ACOUSTIC_CAPABILITY",
    "API_ENDPOINT_GET_ALL_ROUTINES",
    "DISPLAY_BRIGHTNESS_MIN",
    "DISPLAY_BRIGHTNESS_MAX",
    "DISPLAY_DEFAULT_BRIGHTNESS",
    "API_ENDPOINT_SET_ALARM",
    "API_ENDPOINT_GET_ALARM",
    "API_ENDPOINT_ALARM_STOP",
    "API_ENDPOINT_TIME_SYNC",
    "API_ENDPOINT_SET_SHUTDOWN",
    "API_ENDPOINT_GET_SHUTDOWN",
    "ALARM_TRIGGER_CANCEL",
    "ALARM_TRIGGER_ONCE",
    "ALARM_TRIGGER_DAILY",
    "ALARM_TRIGGER_WEEKLY",
    "ALARM_TRIGGER_WEEKLY_BITMASK",
    "ALARM_TRIGGER_MONTHLY",
    "ALARM_OP_SHELL",
    "ALARM_OP_PLAYBACK",
    "ALARM_OP_STOP",
    "PLAY_MODE_NORMAL",
    "PLAY_MODE_REPEAT_ALL",
    "PLAY_MODE_REPEAT_ONE",
    "PLAY_MODE_SHUFFLE",
    "PLAY_MODE_SHUFFLE_REPEAT_ALL",
    # Subwoofer endpoints and constants
    "API_ENDPOINT_SUBWOOFER_STATUS",
    "API_ENDPOINT_SUBWOOFER_SET",
    "SUBWOOFER_CROSSOVER_MIN",
    "SUBWOOFER_CROSSOVER_MAX",
    "SUBWOOFER_LEVEL_MIN",
    "SUBWOOFER_LEVEL_MAX",
    "SUBWOOFER_DELAY_MIN",
    "SUBWOOFER_DELAY_MAX",
    "SUBWOOFER_PHASE_0",
    "SUBWOOFER_PHASE_180",
    # PEQ (Parametric EQ) endpoints and constants
    "API_ENDPOINT_PEQ_GET_BAND",
    "API_ENDPOINT_PEQ_GET_SOURCE_BAND",
    "API_ENDPOINT_PEQ_SET_BAND",
    "API_ENDPOINT_PEQ_SET_SOURCE_BAND",
    "API_ENDPOINT_PEQ_CHANGE_FX",
    "API_ENDPOINT_PEQ_CHANGE_SOURCE_FX",
    "API_ENDPOINT_PEQ_SOURCE_OFF",
    "API_ENDPOINT_PEQ_GET_LIST",
    "API_ENDPOINT_PEQ_GET_NEW_LIST",
    "API_ENDPOINT_PEQ_SAVE",
    "API_ENDPOINT_PEQ_SOURCE_SAVE",
    "API_ENDPOINT_PEQ_LOAD",
    "API_ENDPOINT_PEQ_SOURCE_LOAD",
    "API_ENDPOINT_PEQ_DELETE",
    "API_ENDPOINT_PEQ_RENAME",
    "API_ENDPOINT_PEQ_SET_CHANNEL_MODE",
    "PEQ_PLUGIN_URI",
    "PEQ_BAND_LETTERS",
    "PEQ_DEFAULT_FREQUENCIES",
    "PEQ_MODE_OFF",
    "PEQ_MODE_LOW_SHELF",
    "PEQ_MODE_PEAK",
    "PEQ_MODE_HIGH_SHELF",
    "PEQ_FREQ_MIN",
    "PEQ_FREQ_MAX",
    "PEQ_Q_MIN",
    "PEQ_Q_MAX",
    "PEQ_GAIN_MIN",
    "PEQ_GAIN_MAX",
    "PEQ_DEFAULT_MODE",
    "PEQ_DEFAULT_Q",
    "PEQ_DEFAULT_GAIN",
    "PEQ_CHANNEL_MODE_STEREO",
    "PEQ_CHANNEL_MODE_LR",
]
