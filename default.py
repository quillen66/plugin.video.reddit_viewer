#!/usr/bin/python
# encoding: utf-8
import urllib
import urllib2
import socket
import sys
import re
import os
import json
import sqlite3
import random
import datetime
import time
import xbmc
import xbmcplugin
import xbmcgui
import xbmcaddon
import urlparse
import pprint

#import SimpleDownloader
import requests

import threading

#this import for the youtube_dl addon causes our addon to start slower. we'll import it when we need to playYTDLVideo
modes_that_use_ytdl=['mode=playYTDLVideo','mode=play']
try:
    if any(mode in sys.argv[2] for mode in modes_that_use_ytdl):   ##if 'mode=playYTDLVideo' in sys.argv[2] :
        import YDStreamExtractor      #note: you can't just add this import in code, you need to re-install the addon with <import addon="script.module.youtube.dl"        version="16.521.0"/> in addon.xml
except:
    pass

#YDStreamExtractor.disableDASHVideo(True) #Kodi (XBMC) only plays the video for DASH streams, so you don't want these normally. Of course these are the only 1080p streams on YouTube
from urllib import urlencode

import urlresolver

reload(sys)
sys.setdefaultencoding("utf-8")


addon         = xbmcaddon.Addon()
addon_path    = addon.getAddonInfo('path')
pluginhandle  = int(sys.argv[1])
addonID       = addon.getAddonInfo('id')  #plugin.video.reddit_viewer

WINDOW        = xbmcgui.Window(10000)
#technique borrowed from LazyTV.
#  WINDOW is like a mailbox for passing data from caller to callee.
#    e.g.: addLink() needs to pass "image description" to playSlideshow()

osWin         = xbmc.getCondVisibility('system.platform.windows')
osOsx         = xbmc.getCondVisibility('system.platform.osx')
osLinux       = xbmc.getCondVisibility('system.platform.linux')

if osWin:
    fd="\\"
else:
    fd="/"

socket.setdefaulttimeout(30)
opener = urllib2.build_opener()
#opener = urllib2.build_opener(urllib2.HTTPHandler(debuglevel=1))

#https://github.com/reddit/reddit/wiki/API
reddit_userAgent = "XBMC:"+addonID+":v"+addon.getAddonInfo('version')+" (by /u/gsonide)"
reddit_clientID      ="hXEx62LGqxLj8w"
reddit_redirect_uri  ='http://localhost:8090/'   #specified when registering for a clientID
reddit_refresh_token =addon.getSetting("reddit_refresh_token")
reddit_access_token  =addon.getSetting("reddit_access_token") #1hour token

#test1 line

opener.addheaders = [('User-Agent', reddit_userAgent)]
#API requests with a bearer token should be made to https://oauth.reddit.com, NOT www.reddit.com.
urlMain = "https://www.reddit.com"


#filter           = addon.getSetting("filter") == "true"
#filterRating     = int(addon.getSetting("filterRating"))
#filterThreshold  = int(addon.getSetting("filterThreshold"))

autoplayAll          = addon.getSetting("autoplayAll") == "true"
autoplayUnwatched    = addon.getSetting("autoplayUnwatched") == "true"
autoplayUnfinished   = addon.getSetting("autoplayUnfinished") == "true"
autoplayRandomize    = addon.getSetting("autoplayRandomize") == "true"

forceViewMode        = addon.getSetting("forceViewMode") == "true"
viewMode             = str(addon.getSetting("viewMode"))
comments_viewMode    = str(addon.getSetting("comments_viewMode"))
album_viewMode       = str(addon.getSetting("album_viewMode"))

#this part moved to in domains.py
#hide_IMG              = addon.getSetting("hide_IMG") == "true"
#hide_reddit           = addon.getSetting("hide_reddit") == "true"
#hide_undetermined     = addon.getSetting("hide_undetermined") == "true"
#hide_video            = addon.getSetting("hide_video") == "true"
#resolve_undetermined  = addon.getSetting("resolve_undetermined") == "true"

hide_nsfw            = addon.getSetting("hide_nsfw") == "true"
domain_filter        = addon.getSetting("domain_filter")
subreddit_filter     = addon.getSetting("subreddit_filter")

r_AccessToken         = addon.getSetting("r_AccessToken")

sitemsPerPage        = addon.getSetting("itemsPerPage")
try: itemsPerPage = int(sitemsPerPage)
except: itemsPerPage = 50

itemsPerPage          = ["10", "25", "50", "75", "100"][itemsPerPage]
TitleAddtlInfo        = addon.getSetting("TitleAddtlInfo") == "true"   #Show additional post info on title</string>
HideImagePostsOnVideo = addon.getSetting("HideImagePostsOnVideo") == 'true' #<string id="30204">Hide image posts on video addon</string>
setting_hide_images = False

DoNotResolveLinks     = addon.getSetting("DoNotResolveLinks") == 'true'

#--- settings related to context menu "Show Comments"
CommentTreshold          = addon.getSetting("CommentTreshold")
try: int_CommentTreshold = int(CommentTreshold)
except: int_CommentTreshold = -1000    #if CommentTreshold can't be converted to int, show all comments

#showBrowser     = addon.getSetting("showBrowser") == "true"
#browser_win     = int(addon.getSetting("browser_win"))
#browser_wb_zoom = str(addon.getSetting("browser_wb_zoom"))

try:istreamable_quality=int(addon.getSetting("streamable_quality"))  #values 0 or 1
except:istreamable_quality=0
streamable_quality  =["full", "mobile"][istreamable_quality]       #https://streamable.com/documentation

addonUserDataFolder = xbmc.translatePath("special://profile/addon_data/"+addonID)
subredditsFile      = xbmc.translatePath("special://profile/addon_data/"+addonID+"/subreddits")
subredditsPickle    = xbmc.translatePath("special://profile/addon_data/"+addonID+"/subreddits.pickle")  #new type of saving the settings

REQUEST_TIMEOUT=5 #requests.get timeout in seconds

#C:\Users\myusername\AppData\Roaming\Kodi\userdata\addon_data\plugin.video.reddit_viewer
#SlideshowCacheFolder    = xbmc.translatePath("special://profile/addon_data/"+addonID+"/slideshowcache") #will use this to cache images for slideshow in video mode

if not os.path.isdir(addonUserDataFolder):
    os.mkdir(addonUserDataFolder)

def json_query(query, ret):
    try:
        xbmc_request = json.dumps(query)
        result = xbmc.executeJSONRPC(xbmc_request)
        #print result
        #result = unicode(result, 'utf-8', errors='ignore')
        #log('result = ' + str(result))
        if ret:
            return json.loads(result)['result']
        else:
            return json.loads(result)
    except:
        return {}

def getDbPath():
    path = xbmc.translatePath("special://userdata/Database")
    files = os.listdir(path)
    latest = ""
    for file in files:
        if file[:8] == 'MyVideos' and file[-3:] == '.db':
            if file > latest:
                latest = file
    if latest:
        return os.path.join(path, latest)
    else:
        return ""

def getPlayCount(url):
    if dbPath:
        #log(url[:120])
        #c.execute('SELECT playCount FROM files WHERE strFilename LIKE ?', [url[:100]])

        str_sql='SELECT playCount FROM files WHERE strFilename LIKE ?'
        args=[url[:120]+'%']

        #str_sql='SELECT playCount FROM files WHERE strFilename = ?'
        #args=[url]

        c.execute(str_sql,args)


        result = c.fetchone()
        #log('*****************'+repr(result) )
        if result:
            result = result[0]
            if result:
                return int(result)
            return 0
    return -1

#def getPlayCount(url):
#
#    #query   = '{"jsonrpc": "2.0","method": "VideoLibrary.GetTVShows","params": {"filter": {"field": "playcount", "operator": "is", "value": "0" },"properties": ["lastplayed"], "sort": {"order": "descending", "method": "lastplayed"} },"id": "1" }'
#    #request = '{"jsonrpc": "2.0","method": "VideoLibrary.GetMovies", "params": {"filter": {"field": "playcount", "operator": "greaterthan", "value": "0"},  "limits": { "start" : 0 }, "properties": ["playcount"], "sort": { "order": "ascending", "method": "label" } }, "id": "libMovies"}'
#    #request='{"jsonrpc": "2.0", "method": "Player.GetItem", "params": { "properties": ["title", "album", "artist", "season", "episode", "duration", "showtitle", "tvshowid", "thumbnail", "file", "fanart", "streamdetails"], "playerid": 1}, "id": "VideoGetItem"}'
#
#    #results = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
#
##    get_movies       = {"jsonrpc": "2.0",'id': 1, "method": "VideoLibrary.GetMovies",     "params": { "filter": {"field": "playcount", "operator": "is", "value": "0"}, "properties" : ["playcount", "title"] }}
##
##    mov = json_query(get_movies, True)
##    log(repr(mov))
#
#    request = {"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": { "filter": {"field": "playcount", "operator": "greaterthan", "value": "0"}, "limits": { "start" : 0 }, "properties": ["playcount"], "sort": { "order": "ascending", "method": "label" } }, "id": url}
#    results = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
#    log(repr(results))

#MODE addSubreddit      - name, type not used
def addSubreddit(subreddit, name, type):
    from resources.lib.utils import this_is_a_multireddit, format_multihub, colored_subreddit
    alreadyIn = False
    fh = open(subredditsFile, 'r')
    content = fh.readlines()
    fh.close()
    if subreddit:
        for line in content:
            if line.lower()==subreddit.lower():
                alreadyIn = True
        if not alreadyIn:
            with open(subredditsFile, 'a') as fh:
                fh.write(subreddit+'\n')

            get_subreddit_entry_info(subreddit)
        xbmc.executebuiltin('XBMC.Notification("%s", "%s" )' %( colored_subreddit(subreddit), translation(30019)  ) )
    else:
        #dialog = xbmcgui.Dialog()
        #ok = dialog.ok('Add subreddit', 'Add a subreddit (videos)','or  Multiple subreddits (music+listentothis)','or  Multireddit (/user/.../m/video)')
        #would be great to have some sort of help to show first time user here

        keyboard = xbmc.Keyboard('', translation(30001))
        keyboard.doModal()
        if keyboard.isConfirmed() and keyboard.getText():
            subreddit = keyboard.getText()

            #cleanup user input. make sure /user/ and /m/ is lowercase
            if this_is_a_multireddit(subreddit):
                subreddit = format_multihub(subreddit)
            else:
                get_subreddit_entry_info(subreddit)


            for line in content:
                if line.lower()==subreddit.lower()+"\n":
                    alreadyIn = True

            if not alreadyIn:
                fh = open(subredditsFile, 'a')
                fh.write(subreddit+'\n')
                fh.close()
        xbmc.executebuiltin("Container.Refresh")

def get_subreddit_entry_info(subreddit):
    #from resources.lib.utils import get_subreddit_info, parse_subreddit_entry, create_default_subreddits, load_dict
    if subreddit.lower() in ['all','random','randnsfw']:
        return
    s=[]
    if '/' in subreddit:  #we want to get diy from diy/top or diy/new
        subreddit=subreddit.split('/')[0]

    if '+' in subreddit:
        s.extend(subreddit.split('+'))
    else:
        s.append(subreddit)

    t = threading.Thread(target=get_subreddit_entry_info_thread, args=(s,) )
    #threads.append(t)
    #log('****starting... '+repr(t))
    t.start()

def get_subreddit_entry_info_thread(sub_list):
    from resources.lib.utils import get_subreddit_info, load_dict, save_dict

    subreddits_dlist=[]
    #log('**** thread running')
    if os.path.exists(subredditsPickle):
        #log('****file exists ' + repr( subredditsPickle ))
        subreddits_dlist=load_dict(subredditsPickle)
        #for e in subreddits_dlist: log(e.get('entry_name'))
        #log( pprint.pformat(subreddits_dlist, indent=1) )

    #log('****------before for -------- ' + repr(sub_list ))
    for subreddit in sub_list:
        #remove old instance of subreddit
        subreddits_dlist=[x for x in subreddits_dlist if x.get('entry_name') != subreddit.lower() ]

        #for e in subreddits_dlist: log(e.get('entry_name'))

        #log('****getting sub_info ' )

        sub_info=get_subreddit_info(subreddit)

        log('****sub_info ' + repr( sub_info ))

        if sub_info:
            #log('****if sub_info ')
            subreddits_dlist.append(sub_info)
            save_dict(subreddits_dlist, subredditsPickle)
            #log('****saved ')

#MODE removeSubreddit      - name, type not used
def removeSubreddit(subreddit, name, type):
    #note: calling code in addDirR()
    fh = open(subredditsFile, 'r')
    content = fh.readlines()
    fh.close()
    contentNew = ""
    for line in content:
        if line!=subreddit+'\n':
            #log('line='+line+'toremove='+subreddit)
            contentNew+=line
    fh = open(subredditsFile, 'w')
    fh.write(contentNew)
    fh.close()
    xbmc.executebuiltin("Container.Refresh")

def editSubreddit(subreddit, name, type):
    from resources.lib.utils import this_is_a_multireddit, format_multihub
    #note: calling code in addDirR()
    fh = open(subredditsFile, 'r')
    content = fh.readlines()
    fh.close()
    contentNew = ""

    keyboard = xbmc.Keyboard(subreddit, translation(30003))
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        newsubreddit = keyboard.getText()
        #cleanup user input. make sure /user/ and /m/ is lowercase
        if this_is_a_multireddit(newsubreddit):
            newsubreddit = format_multihub(newsubreddit)
        else:
            get_subreddit_entry_info(newsubreddit)

        for line in content:
            if line.strip()==subreddit.strip() :      #if matches the old subreddit,
                #log("adding: %s  %s  %s" %(line, subreddit, newsubreddit)  )
                contentNew+=newsubreddit+'\n'
            else:
                contentNew+=line

        fh = open(subredditsFile, 'w')
        fh.write(contentNew)
        fh.close()

        xbmc.executebuiltin("Container.Refresh")

def index(url,name,type):
    from resources.lib.utils import load_subredditsFile, parse_subreddit_entry, create_default_subreddits, assemble_reddit_filter_string,xstr, ret_sub_info, samealphabetic, hassamealphabetic

    ## this is where the main screen is created
    content = ""
    if not os.path.exists(subredditsFile):  #if not os.path.exists(subredditsFile):
        create_default_subreddits()

    #if os.path.exists(subredditsPickle):
    #    subreddits_dlist=load_dict(subredditsPickle)
    #log( pprint.pformat(subreddits_dlist, indent=1) )
    #for e in subreddits_dlist: log(e.get('entry_name'))

    #testing code
    #h="as asd [S]asdasd[/S] asdas "
    #log(markdown_to_bbcode(h))
    #addDir('test', "url", "next_mode", "", "subreddit" )

    #link='http://mylust.com/videos/433093/this-exotic-honey-has-spent-a-lot-of-time-perfecting-her-pussy-fingering-skills/'
    #from resources.lib.youtube_dl import YoutubeDL

    #ytb = YoutubeDL({'format': 'bestvideo+bestaudio/best',\
    #                               "quiet": True,\
    #                               "nocheckcertificate": True})
    #with ytb:
    #    result = ytb.extract_info(link, download=False)
    #    log('ytb result'+repr(result))

    #liz = xbmcgui.ListItem(label="test", label2="label2", iconImage="DefaultFolder.png")
    #u=sys.argv[0]+"?url=&mode=callwebviewer&type="
    #xbmcplugin.addDirectoryItem(handle=pluginhandle, url=u, listitem=liz, isFolder=False)

    #liz = xbmcgui.ListItem().fromString('Hello World')
    #xbmcplugin.addDirectoryItem(handle=pluginhandle, listitem=liz, isFolder=False)
    subredditsFile_entries=load_subredditsFile()

    subredditsFile_entries.sort(key=lambda y: y.lower())

    addtl_subr_info={}

    #this controls what infolabels will be used by the skin. very skin specific.
    #  for estuary, this lets infolabel:plot (and genre) show up below the folder
    #  giving us the opportunity to provide a shortcut_description about the shortcuts
    xbmcplugin.setContent(pluginhandle, "mixed") #files, songs, artists, albums, movies, tvshows, episodes, musicvideos

    next_mode='listSubReddit'

    for subreddit_entry in subredditsFile_entries:
        #strip out the alias identifier from the subreddit string retrieved from the file so we can process it.
        #subreddit, alias = subreddit_alias(subreddit_entry)
        addtl_subr_info=ret_sub_info(subreddit_entry)

        entry_type, subreddit, alias, shortcut_description=parse_subreddit_entry(subreddit_entry)
        #log( subreddit + "   " + shortcut_description )

        #url= urlMain+"/r/"+subreddit+"/.json?"+nsfw+allHosterQuery+"&limit="+itemsPerPage
        url= assemble_reddit_filter_string("",subreddit, "yes")
        #log("assembled================="+url)
        if subreddit.lower() == "all":
            addDir(subreddit, url, next_mode, "", subreddit, { "plot": translation(30009) } )  #Displays the currently most popular content from all of reddit....
        else:
            if addtl_subr_info: #if we have additional info about this subreddit
                title=addtl_subr_info.get('title')+'\n'
                display_name=xstr(addtl_subr_info.get('display_name'))
                if samealphabetic( title, display_name): title=''
                #if re.sub('\W+','', display_name.lower() )==re.sub('\W+','', title.lower()): title=''
                #display_name=re.sub('\W+','', display_name.lower() )
                #title=re.sub('\W+','', title.lower())

                header_title=xstr(addtl_subr_info.get('header_title'))
                public_description=xstr( addtl_subr_info.get('public_description'))

                if samealphabetic( header_title, public_description): public_description=''
                if samealphabetic(title,public_description): public_description=''
                #if hassamealphabetic(header_title,title,public_description): public_description=''

                shortcut_description='[COLOR cadetblue][B]r/%s[/B][/COLOR]\n%s[I]%s[/I]\n%s' %(display_name,title,header_title,public_description )

                icon=addtl_subr_info.get('icon_img')
                banner=addtl_subr_info.get('banner_img')
                header=addtl_subr_info.get('header_img')  #usually the small icon on upper left side on subreddit screen

                #log( subreddit + ' icon=' + repr(icon) +' header=' + repr(header))
                #picks the first item that is not None
                icon=next((item for item in [icon,banner,header] if item ), '')

                addDirR(alias, url, next_mode, icon,
                        type=subreddit,
                        listitem_infolabel={ "plot": shortcut_description },
                        file_entry=subreddit_entry,
                        banner_image=banner )
            else:
                addDirR(alias, url, next_mode, "", subreddit, { "plot": shortcut_description }, subreddit_entry )

    addDir("[B]- "+translation(30001)+"[/B]", "", 'addSubreddit', "", "", { "plot": translation(30006) } ) #"Customize this list with your favorite subreddit."
    addDir("[B]- "+translation(30005)+"[/B]", "",'searchReddits', "", "", { "plot": translation(30010) } ) #"Search reddit for a particular post or topic

    xbmcplugin.endOfDirectory(pluginhandle)

def listSubReddit(url, name, subreddit_key):
    from resources.lib.utils import unescape, strip_emoji, pretty_datediff, post_is_filtered_out, ret_sub_icon, has_multiple_subreddits
    #url=r'https://www.reddit.com/r/videos/search.json?q=nsfw:yes+site%3Ayoutu.be+OR+site%3Ayoutube.com+OR+site%3Avimeo.com+OR+site%3Aliveleak.com+OR+site%3Adailymotion.com+OR+site%3Agfycat.com&sort=relevance&restrict_sr=on&limit=5&t=week'
    #url='https://www.reddit.com/search.json?q=site%3Adailymotion&restrict_sr=&sort=relevance&t=week'

    #show_listVideos_debug=False
    show_listVideos_debug=True
    credate = ""
    is_a_video=False
    title_line2=""
    log("listSubReddit subreddit=%s url=%s" %(subreddit_key,url) )
    t_on = translation(30071)  #"on"
    #t_pts = u"\U0001F4AC"  # translation(30072) #"cmnts"  comment bubble symbol. doesn't work
    #t_pts = u"\U00002709"  # translation(30072)   envelope symbol
    t_pts='c'

    thumb_w=0
    thumb_h=0

    currentUrl = url
    xbmcplugin.setContent(pluginhandle, "movies") #files, songs, artists, albums, movies, tvshows, episodes, musicvideos


    dialog_progress = xbmcgui.DialogProgressBG()
    dialog_progress_heading='Loading'
    dialog_progress.create(dialog_progress_heading )
    dialog_progress.update(0,dialog_progress_heading, subreddit_key  )

    content = reddit_request(url)

    if not content:
        return

    page_title="[COLOR cadetblue]%s[/COLOR]" %subreddit_key

    #setPluginCategory lets us show text at the top of window, we take advantage of this and put the subreddit name
    xbmcplugin.setPluginCategory(pluginhandle, page_title)

    info_label={ "plot": translation(30013) }  #Automatically play videos
    if autoplayAll:       addDir("[B]- "+translation(30016)+"[/B]", url, 'autoPlay', "", "ALL", info_label)
    if autoplayUnwatched: addDir("[B]- "+translation(30017)+"[/B]" , url, 'autoPlay', "", "UNWATCHED", info_label)

    #7-15-2016  removed the "replace(..." statement below cause it was causing error
    #content = json.loads(content.replace('\\"', '\''))
    content = json.loads(content)

    #log("query returned %d items " % len(content['data']['children']) )
    posts_count=len(content['data']['children'])

    hms = has_multiple_subreddits(content['data']['children'])

    for idx, entry in enumerate(content['data']['children']):
        try:
            if post_is_filtered_out( entry ):
                continue

            title = unescape(entry['data']['title'].encode('utf-8'))
            title = strip_emoji(title) #an emoji in the title was causing a KeyError  u'\ud83c'

            try:    description = unescape(entry['data']['media']['oembed']['description'].encode('utf-8'))
            except: description = ''
            #log('    description  [%s]' %description)
            try:    post_selftext=unescape(entry['data']['selftext'].encode('utf-8'))
            except: post_selftext=''

            description=post_selftext+'[CR]'+description if post_selftext else description

            commentsUrl = urlMain+entry['data']['permalink'].encode('utf-8')
            #if show_listVideos_debug :log("commentsUrl"+str(idx)+"="+commentsUrl)

            try:
                aaa = entry['data']['created_utc']
                credate = datetime.datetime.utcfromtimestamp( aaa )
                #log("creation_date="+str(credate))

                ##from datetime import datetime
                #now = datetime.datetime.now()
                #log("     now_date="+str(now))
                ##from dateutil import tz
                now_utc = datetime.datetime.utcnow()
                #log("     utc_date="+str(now_utc))
                #log("  pretty_date="+pretty_datediff(now_utc, credate))
                pretty_date=pretty_datediff(now_utc, credate)
                credate = str(credate)
            except:
                credate = ""
                credateTime = ""

            subreddit=entry['data']['subreddit'].encode('utf-8')
            #if show_listVideos_debug :log("  SUBREDDIT"+str(idx)+"="+subreddit)

            try: author = entry['data']['author'].encode('utf-8')
            except: author = ""
            #if show_listVideos_debug :log("     AUTHOR"+str(idx)+"="+author)

            try: domain= entry['data']['domain'].encode('utf-8')
            except: domain = ""
            #log("     DOMAIN%.2d=%s" %(idx,domain))

            ups = entry['data']['score']       #downs not used anymore
            try:num_comments = entry['data']['num_comments']
            except:num_comments = 0

            #description = "[COLOR blue]r/"+ subreddit + "[/COLOR]  [I]" + str(ups)+" pts  |  "+str(comments)+" cmnts  |  by "+author+"[/I]\n"+description
            #description = "[COLOR blue]r/"+ subreddit + "[/COLOR]  [I]" + str(ups)+" pts.  |  by "+author+"[/I]\n"+description
            #description = title_line2+"\n"+description
            #if show_listVideos_debug :log("DESCRIPTION"+str(idx)+"=["+description+"]")
            try:
                media_url = entry['data']['url'].encode('utf-8')
            except:
                media_url = entry['data']['media']['oembed']['url'].encode('utf-8')

            thumb = entry['data']['thumbnail'].encode('utf-8')
            #if show_listSubReddit_debug : log("       THUMB%.2d=%s" %( idx, thumb ))

            if thumb in ['nsfw','default','self']:  #reddit has a "default" thumbnail (alien holding camera with "?")
                thumb=""

            if thumb=="":
                try: thumb = entry['data']['media']['oembed']['thumbnail_url'].encode('utf-8').replace('&amp;','&')
                except: pass

            if thumb=="":  #use this subreddit's icon if thumb still empty
                try: thumb=ret_sub_icon(subreddit)
                except: pass

            try:
                #collect_thumbs(entry)
                preview=entry['data']['preview']['images'][0]['source']['url'].encode('utf-8').replace('&amp;','&')
                #poster = entry['data']['media']['oembed']['thumbnail_url'].encode('utf-8')
                #t=thumb.split('?')[0]
                #can't preview gif thumbnail on thumbnail view, use alternate provided by reddit
                #if t.endswith('.gif'):
                    #log('  thumb ends with .gif')
                #    thumb = entry['data']['thumbnail'].encode('utf-8')
                try:
                    thumb_h = float( entry['data']['preview']['images'][0]['source']['height'] )
                    thumb_w = float( entry['data']['preview']['images'][0]['source']['width'] )
                except:
                    thumb_w=0
                    thumb_h=0

            except Exception as e:
                #log("   getting preview image EXCEPTION:="+ str( sys.exc_info()[0]) + "  " + str(e) )
                thumb_w=0
                thumb_h=0
                preview="" #a blank preview image will be replaced with poster_url from make_addon_url_from() for domains that support it

            is_a_video = determine_if_video_media_from_reddit_json(entry)

            try:
                over_18 = entry['data']['over_18']
            except:
                over_18 = False

            #setting: toggle showing 2-line title
            #log("   TitleAddtlInfo "+str(idx)+"="+str(TitleAddtlInfo))
            title_line2=""
            #if TitleAddtlInfo:
            #title_line2 = "[I][COLOR dimgrey]%s by %s [COLOR darkslategrey]r/%s[/COLOR] %d pts.[/COLOR][/I]" %(pretty_date,author,subreddit,ups)
            #title_line2 = "[I][COLOR dimgrey]"+pretty_date+" by "+author+" [COLOR darkslategrey]r/"+subreddit+"[/COLOR] "+str(ups)+" pts.[/COLOR][/I]"

            title_line2 = "[I][COLOR dimgrey]%s %s [COLOR cadetblue]r/%s[/COLOR] (%d) %s[/COLOR][/I]" %(pretty_date,t_on, subreddit,num_comments, t_pts)
            #title_line2 = "[I]"+str(idx)+". [COLOR dimgrey]"+ media_url[0:50]  +"[/COLOR][/I] "  # +"    "+" [COLOR darkslategrey]r/"+subreddit+"[/COLOR] "+str(ups)+" pts.[/COLOR][/I]"

            #if show_listVideos_debug : log( ("v" if is_a_video else " ") +"     TITLE"+str(idx)+"="+title)
            if show_listVideos_debug : log("  POST%cTITLE%.2d=%s" %( ("v" if is_a_video else " "), idx, title ))
            #if show_listVideos_debug :log("      OVER_18"+str(idx)+"="+str(over_18))
            #if show_listVideos_debug :log("   IS_A_VIDEO"+str(idx)+"="+str(is_a_video))
            #if show_listVideos_debug :log("        THUMB"+str(idx)+"="+thumb)
            #if show_listVideos_debug :log("    MediaURL%.2d=%s" % (idx,media_url) )

            #if show_listVideos_debug :log("       HOSTER"+str(idx)+"="+hoster)
            #log("    VIDEOID"+str(idx)+"="+videoID)
            #log( "["+description+"]1["+ str(date)+"]2["+ str( count)+"]3["+ str( commentsUrl)+"]4["+ str( subreddit)+"]5["+ video_url +"]6["+ str( over_18))+"]"

            loading_percentage=int((float(idx)/posts_count)*100)
            dialog_progress.update( loading_percentage,dialog_progress_heading, title  )

            addLink(title=title,
                    title_line2=title_line2,
                    iconimage=thumb,
                    previewimage=preview,
                    preview_w=thumb_w,
                    preview_h=thumb_h,
                    domain=domain,
                    description=description,
                    credate=credate,
                    reddit_says_is_video=is_a_video,
                    site=commentsUrl,
                    subreddit=subreddit,
                    media_url=media_url,
                    over_18=over_18,
                    posted_by=author,
                    num_comments=num_comments,
                    post_index=idx,
                    post_total=posts_count,
                    many_subreddit=hms)
        except Exception as e:
            log(" EXCEPTION:="+ str( sys.exc_info()[0]) + "  " + str(e) )
            pass

    #log("**reddit query returned "+ str(idx) +" items")
    #window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    #log("focusid:"+str(window.getFocusId()))
    dialog_progress.update( 100,dialog_progress_heading  )
    dialog_progress.close() #it is important to close xbmcgui.DialogProgressBG

    try:
        #this part makes sure that you load the next page instead of just the first
        after=""
        after = content['data']['after']
        if "&after=" in currentUrl:
            nextUrl = currentUrl[:currentUrl.find("&after=")]+"&after="+after
        else:
            nextUrl = currentUrl+"&after="+after

        # plot shows up on estuary. etc. ( avoids the "No information available" message on description )
        info_label={ "plot": translation(30004) + '[CR]' + page_title}
        addDir(translation(30004), nextUrl, 'listSubReddit', "", subreddit_key,info_label)   #Next Page
        #if show_listVideos_debug :log("NEXT PAGE="+nextUrl)
    except:
        pass

    #the +'s got removed by url conversion
    subreddit_key=subreddit_key.replace(' ','+')
    viewID=WINDOW.getProperty( "viewid-"+subreddit_key )
    #log("  custom viewid %s for %s " %(viewID,subreddit_key) )

    if viewID:
        log("  custom viewid %s for %s " %(viewID,subreddit_key) )
        xbmc.executebuiltin('Container.SetViewMode(%s)' %viewID )
    else:
        if forceViewMode:
            xbmc.executebuiltin('Container.SetViewMode('+viewMode+')')

    xbmcplugin.endOfDirectory(handle=pluginhandle,
                              succeeded=True,
                              updateListing=False,   #setting this to True causes the ".." entry to quit the plugin
                              cacheToDisc=True)

def addLink(title, title_line2, iconimage, previewimage,preview_w,preview_h,domain,description, credate, reddit_says_is_video, site, subreddit, media_url, over_18, posted_by="", num_comments=0,post_index=1,post_total=1,many_subreddit=False ):
    from resources.lib.utils import ret_info_type_icon, assemble_reddit_filter_string,build_script,subreddit_in_favorites, colored_subreddit
    from resources.lib.domains import parse_reddit_link, build_DirectoryItem_url_based_on_media_type

    videoID=""
    post_title=title
    il_description=""
    n=""  #will hold red nsfw asterisk string
    h=""  #will hold bold hoster:  string
    t_Album = translation(30073) if translation(30073) else "Album"
    t_IMG =  translation(30074) if translation(30074) else "IMG"

    ok = False

    isFolder=True
    thumb_url=''

    colored_subreddit=colored_subreddit(subreddit)

    h="[B]" + domain + "[/B]: "
    if over_18:
        mpaa="R"
        n = "[COLOR red]*[/COLOR] "
        #description = "[B]" + hoster + "[/B]:[COLOR red][NSFW][/COLOR] "+title+"\n" + description
        il_description = "[COLOR red][NSFW][/COLOR] "+ h+title+"[CR]" + "[COLOR grey]" + description + "[/COLOR]"
    else:
        mpaa=""
        n=""
        il_description = h+title+"[CR]" + "[COLOR grey]" + description + "[/COLOR]"

    if TitleAddtlInfo:     #put the additional info on the description if setting set to single line titles
        log( repr(title_line2 ))
        post_title=n+title+"[CR]"+title_line2
    else:
        post_title=n+title
        il_description=title_line2+"[CR]"+il_description

    il={"title": post_title, "plot": il_description, "plotoutline": il_description, "Aired": credate, "mpaa": mpaa, "Genre": "r/"+subreddit, "studio": domain, "director": posted_by }   #, "duration": 1271}   (duration uses seconds for titan skin

    liz=xbmcgui.ListItem(label=post_title,
                          label2="",
                          iconImage="",
                          thumbnailImage='')

    #this is a video plugin, set type to video so that infolabels show up.
    liz.setInfo(type='video', infoLabels=il)

    if iconimage in ["","nsfw", "default"]:
        #log( title+ ' iconimage blank['+iconimage+']['+thumb_url+ ']media_url:'+media_url )
        iconimage=thumb_url

    preview_ar=0.0
    if (preview_w==0 or preview_h==0) != True:
        preview_ar=float(preview_w) / preview_h
        #log("preview ar: "+ repr(preview_ar))

    if previewimage: needs_preview=False
    else:            needs_preview=True  #reddit has no thumbnail for this link. please get one

    #DirectoryItem_url=sys.argv[0]+"?url="+ urllib.quote_plus(media_url) +"&mode=play"

    if DoNotResolveLinks:
        ld=None
        DirectoryItem_url=sys.argv[0]\
            +"?url="+ urllib.quote_plus(media_url) \
            +"&name="+urllib.quote_plus(title) \
            +"&mode=play"
        setProperty_IsPlayable='true'
        isFolder=False
        title_prefix=''
    else:
        ld=parse_reddit_link(media_url,reddit_says_is_video, needs_preview, False, preview_ar  )

        queried_preview_image=ld.poster if ld else iconimage
        if previewimage=="":
           previewimage=queried_preview_image

        arg_name=title
        arg_type=previewimage
        if ld:
            #log('    ' + ld.media_type + ' -> ' + ld.link_action )
            #log('    ***icon:' + ld.thumb + ' -> ' + ld.link_action )
            if iconimage in ["","nsfw", "default"]: iconimage=ld.thumb

        DirectoryItem_url, setProperty_IsPlayable, isFolder, title_prefix = build_DirectoryItem_url_based_on_media_type(ld,
                                                                                                                        media_url,
                                                                                                                        arg_name,
                                                                                                                        arg_type,
                                                                                                                        script_to_call="",
                                                                                                                        on_autoplay=False,
                                                                                                                        img_w=preview_w,
                                                                                                                        img_h=preview_h)
    if title_prefix:
        liz.setLabel( title_prefix+' '+post_title )

    liz.setProperty('IsPlayable', setProperty_IsPlayable)
    liz.setInfo('video', {"title": liz.getLabel(), } )

    liz.setArt({"thumb": iconimage, "poster":previewimage, "banner":iconimage, "fanart":previewimage, "landscape":previewimage, })

    entries = [] #entries for listbox for when you type 'c' or rt-click
    if num_comments > 0:
        #if we are using a custom gui to show comments, we need to use RunPlugin. there is a weird loading/pause if we use XBMC.Container.Update. i think xbmc expects us to use addDirectoryItem
        #  if we have xbmc manage the gui(addDirectoryItem), we need to use XBMC.Container.Update. otherwise we'll get the dreaded "Attempt to use invalid handle -1" error
        #entries.append( ( translation(30050) + " (c)",  #Show comments
        #              "XBMC.RunPlugin(%s?path=%s?prl=zaza&mode=listLinksInComment&url=%s)" % ( sys.argv[0], sys.argv[0], urllib.quote_plus(site) ) ) )
        #entries.append( ( translation(30052) , #Show comment links
        #              "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=listLinksInComment&url=%s&type=linksOnly)" % ( sys.argv[0], sys.argv[0], urllib.quote_plus(site) ) ) )

        entries.append( ( translation(30052) , #Show comment links
                      "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=listLinksInComment&url=%s&type=linksOnly)" % ( sys.argv[0], sys.argv[0], urllib.quote_plus(site) ) ) )
        entries.append( ( translation(30050) ,  #Show comments
                      "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=listLinksInComment&url=%s)" % ( sys.argv[0], sys.argv[0], urllib.quote_plus(site) ) ) )

        #entries.append( ( translation(30050) + " (ActivateWindow)",  #Show comments
        #              "XBMC.ActivateWindow(Video, %s?mode=listLinksInComment&url=%s)" % (  sys.argv[0], urllib.quote_plus(site) ) ) )      #***  ActivateWindow is for the standard xbmc window
    else:
        entries.append( ( translation(30053) ,  #No comments
                      "xbmc.executebuiltin('Action(Close)')" ) )

    #show the "go to other subreddits" if the entire list is from one subreddit
    if many_subreddit:
        #sys.argv[0] is plugin://plugin.video.reddit_viewer/
        #prl=zaza is just a dummy: during testing the first argument is ignored... possible bug?
        entries.append( ( translation(30051)+" %s" %colored_subreddit ,
                          "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=listSubReddit&url=%s)" % ( sys.argv[0], sys.argv[0],urllib.quote_plus(assemble_reddit_filter_string("",subreddit,True)  ) ) ) )
    else:
        #show check /new from this subreddit if it is all the same subreddit
        entries.append( ( translation(30055)+" %s" %colored_subreddit ,
                          "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=listSubReddit&url=%s)" % ( sys.argv[0], sys.argv[0],urllib.quote_plus(assemble_reddit_filter_string("",subreddit+'/new',True)  ) ) ) )

    if not subreddit_in_favorites(subreddit):
        #add selected subreddit to shortcuts
        entries.append( ( translation(30056) %colored_subreddit ,
                          "XBMC.RunPlugin(%s?mode=addSubreddit&url=%s)" % ( sys.argv[0], subreddit ) ) )

    #not working...
    #entries.append( ( translation(30054) ,
    #                  "XBMC.Container.Update(%s?path=%s?prl=zaza&mode=playURLResolver&url=%s)" % ( sys.argv[0], sys.argv[0],urllib.quote_plus(media_url) ) ) )
    #entries.append( ( translation(30054) ,
    #                  "XBMC.RunPlugin(%s?path=%s?prl=zaza&mode=playURLRVideo&url=%s)" % ( sys.argv[0], sys.argv[0], urllib.quote_plus(media_url) ) ) )


    #favEntry = '<favourite name="'+title+'" url="'+DirectoryItem_url+'" description="'+description+'" thumb="'+iconimage+'" date="'+credate+'" site="'+site+'" />'
    #entries.append((translation(30022), 'RunPlugin(plugin://'+addonID+'/?mode=addToFavs&url='+urllib.quote_plus(favEntry)+'&type='+urllib.quote_plus(subreddit)+')',))

    #if showBrowser and (osWin or osOsx or osLinux):
    #    if osWin and browser_win==0:
    #        entries.append((translation(30021), 'RunPlugin(plugin://plugin.program.webbrowser/?url='+urllib.quote_plus(site)+'&mode=showSite&zoom='+browser_wb_zoom+'&stopPlayback=no&showPopups=no&showScrollbar=no)',))
    #    else:
    #        entries.append((translation(30021), 'RunPlugin(plugin://plugin.program.chrome.launcher/?url='+urllib.quote_plus(site)+'&mode=showSite)',))
    liz.addContextMenuItems(entries)
    #log( 'playcount=' + repr(getPlayCount(DirectoryItem_url)))
    xbmcplugin.addDirectoryItem(pluginhandle, DirectoryItem_url, listitem=liz, isFolder=isFolder, totalItems=post_total)

    return ok

def autoPlay(url, name, autoPlay_type):
    from resources.lib.domains import sitesBase, parse_reddit_link, ydtl_get_playable_url, build_DirectoryItem_url_based_on_media_type, setting_gif_repeat_count
    from resources.lib.utils import unescape, post_is_filtered_out
    #collect a list of title and urls as entries[] from the j_entries obtained from reddit
    #then create a playlist from those entries
    #then play the playlist

    gif_repeat_count=setting_gif_repeat_count()

    entries = []
    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    playlist.clear()
    log("**********autoPlay %s*************" %autoPlay_type)
    content = reddit_request(url)
    if not content: return

    content = json.loads(content.replace('\\"', '\''))

    log("Autoplay %s - Parsing %d items" %( autoPlay_type, len(content['data']['children']) )    )

    for j_entry in content['data']['children']:
        try:
            if post_is_filtered_out( j_entry ):
                continue

            title = unescape(j_entry['data']['title'].encode('utf-8'))

            try:
                media_url = j_entry['data']['url']
            except:
                media_url = j_entry['data']['media']['oembed']['url']

            is_a_video = determine_if_video_media_from_reddit_json(j_entry)

            #log("  Title:%s -%c %s"  %( title, ("v" if is_a_video else " "), media_url ) )
            #hoster, DirectoryItem_url, videoID, mode_type, thumb_url,poster_url, isFolder,setInfo_type, IsPlayable=make_addon_url_from(media_url,is_a_video)
            ld=parse_reddit_link(link_url=media_url, assume_is_video=False, needs_preview=False, get_playable_url=True )

            DirectoryItem_url, setProperty_IsPlayable, isFolder, title_prefix = build_DirectoryItem_url_based_on_media_type(ld, media_url, title, on_autoplay=True)

            if ld:
                if ld.media_type not in [sitesBase.TYPE_VIDEO, sitesBase.TYPE_GIF, sitesBase.TYPE_VIDS, sitesBase.TYPE_MIXED]:
                    continue

            autoPlay_type_entries_append( entries, autoPlay_type, title, DirectoryItem_url)
            if ld.media_type == sitesBase.TYPE_GIF:
                for x in range( 0, gif_repeat_count ):
                    autoPlay_type_entries_append( entries, autoPlay_type, title, DirectoryItem_url)

        except Exception as e:
            log("  EXCEPTION Autoplay "+ str( sys.exc_info()[0]) + "  " + str(e) )

    #def k2(x): return x[1]
    #entries=remove_duplicates(entries, k2)

    if autoplayRandomize:
        random.shuffle(entries)

    #for title, url in entries:
    #    log("  added to playlist:"+ title + "  " + urllib.unquote_plus(url) )
    for title, url in entries:
        listitem = xbmcgui.ListItem(title)
        playlist.add(url, listitem)
        log('add to playlist: %s %s' %(title.ljust(25)[:25],url ))
    xbmc.Player().play(playlist)

def autoPlay_type_entries_append( entries, autoPlay_type, title, playable_url):
    #log(' ****playcount %d:[%s] %s' %( getPlayCount(playable_url), playable_url, title) )
    if autoPlay_type=="ALL":
        entries.append([title,playable_url])
    elif autoPlay_type=="UNWATCHED" and getPlayCount(playable_url) <= 0:
        #log('added to UNWATCHED %s' %( title) )
        entries.append([title,playable_url])
    #elif autoPlay_type.startswith("UNFINISHED_") and getPlayCount(url) == 0:
    #    entries.append([title,playable_url])

def determine_if_video_media_from_reddit_json( entry ):
    #reads the reddit json and determines if link is a video
    is_a_video=False

    try:
        media_url = entry['data']['media']['oembed']['url']   #+'"'
    except:
        media_url = entry['data']['url']   #+'"'

    media_url=media_url.split('?')[0] #get rid of the query string
    try:
        zzz = entry['data']['media']['oembed']['type']
        #log("    zzz"+str(idx)+"="+str(zzz))
        if zzz == None:   #usually, entry['data']['media'] is null for not videos but it is also null for gifv especially nsfw
            if ".gifv" in media_url.lower():  #special case for imgur
                is_a_video=True
            else:
                is_a_video=False
        elif zzz == 'video':
            is_a_video=True
        else:
            is_a_video=False
    except:
        is_a_video=False

    return is_a_video

#MODE playVideo       - name, type not used
def playVideo(url, name, type):
    if url :
        #url='http://i.imgur.com/ARdeL4F.mp4'
        #url='plugin://plugin.video.reddit_viewer/?mode=comments_gui'
        listitem = xbmcgui.ListItem(path=url)
        xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)
    else:
        log("playVideo(url) url is blank")

def playYTDLVideo(url, name, type):
    #url = "http://www.youtube.com/watch?v=_yVv9dx88x0"   #a youtube ID will work as well and of course you could pass the url of another site

    #url='https://www.youtube.com/shared?ci=W8n3GMW5RCY'
    #url='http://burningcamel.com/video/waster-blonde-amateur-gets-fucked'
    #url='http://www.3sat.de/mediathek/?mode=play&obj=51264'
    #url='http://www.4tube.com/videos/209271/hurry-fuck-i-bored'
    #url='http://www.pbs.org/newshour/rundown/cubas-elian-gonzalez-now-college-graduate/'

#these checks done in around May 2016
#does not work:  yourlust  porntube xpornvid.com porndig.com  thumbzilla.com eporner.com yuvutu.com porn.com pornerbros.com fux.com flyflv.com xstigma.com sexu.com 5min.com alphaporno.com
# stickyxtube.com xxxbunker.com bdsmstreak.com  jizzxman.com pornwebms.com pornurl.pw porness.tv openload.online pornworms.com fapgod.com porness.tv hvdporn.com pornmax.xyz xfig.net yobt.com
# eroshare.com kalporn.com hdvideos.porn dailygirlscute.com desianalporn.com indianxxxhd.com onlypron.com sherloxxx.com hdvideos.porn x1xporn.com pornhvd.com lxxlx.com xrhub.com shooshtime.com
# pornvil.com lxxlx.com redclip.xyz younow.com aniboom.com  gotporn.com  virtualtaboo.com 18porn.xyz vidshort.net fapxl.com vidmega.net freudbox.com bigtits.com xfapzap.com orgasm.com
# userporn.com hdpornstar.com moviesand.com chumleaf.com fucktube.com fookgle.com pornative.com dailee.com pornsharia.com fux.com sluttyred.com pk5.net kuntfutube.com youpunish.com
# vidxnet.com jizzbox.com bondagetube.tv spankingtube.tv pornheed.com pornwaiter.com lubetube.com porncor.com maxjizztube.com asianxtv.com analxtv.com yteenporn.com nurglestube.com yporn.tv
# asiantubesex.com zuzandra.com moviesguy.com bustnow.com dirtydirtyangels.com yazum.com watchersweb.com voyeurweb.com zoig.com flingtube.com yourfreeporn.us foxgay.com goshgay.com
# player.moviefap.com(www.moviefap.com works) nosvideo.com

# also does not work (non porn)
# rutube.ru  mail.ru  afreeca.com nicovideo.jp  videos.sapo.pt(many but not all) sciencestage.com vidoosh.tv metacafe.com vzaar.com videojug.com trilulilu.ro tudou.com video.yahoo.com blinkx.com blip.tv
# blogtv.com  brainpop.com crackle.com engagemedia.org expotv.com flickr.com fotki.com hulu.com lafango.com  mefeedia.com motionpictur.com izlesene.com sevenload.com patas.in myvideo.de
# vbox7.com 1tv.ru 1up.com 220.ro 24video.xxx 3sat.de 56.com adultswim.com atresplayer.com techchannel.att.com v.baidu.com azubu.tv www.bbc.co.uk/iplayer bet.com biobiochile.cl biqle.com
# bloomberg.com/news/videos bpb.de bravotv.com byutv.org cbc.ca chirbit.com cloudtime.to(almost) cloudyvideos.com cracked.com crackle.com criterion.com ctv.ca culturebox.francetvinfo.fr
# cultureunplugged.com cwtv.com daum.net dctp.tv democracynow.org douyutv.com dumpert.nl eitb.tv ex.fm fc-zenit.ru  ikudonsubs.com akb48ma.com Flipagram.com ft.dk Formula1.com
# fox.com/watch(few works) video.foxnews.com foxsports.com france2.fr franceculture.fr franceinter.fr francetv.fr/videos francetvinfo.fr giantbomb.com hbo.com History.com hitbox.tv
# howcast.com HowStuffWorks.com hrt.hr iconosquare.com infoq.com  ivi.ru kamcord.com/v video.kankan.com karrierevideos.at KrasView.ru hlamer.ru kuwo.cn la7.it laola1.tv le.com
# media.ccc.de metacritic.com mitele.es  moevideo.net,playreplay.net,videochart.net vidspot.net(might work, can't find recent post) movieclips.com mtv.de mtviggy.com muenchen.tv myspace.com
# myvi.ru myvideo.de myvideo.ge 163.com netzkino.de nfb.ca nicovideo.jp  videohive.net normalboots.com nowness.com ntr.nl nrk.no ntv.ru/video ocw.mit.edu odnoklassniki.ru/video
# onet.tv onionstudios.com/videos openload.co orf.at parliamentlive.tv pbs.org

# news site (can't find sample to test)
# bleacherreport.com crooksandliars.com DailyMail.com channel5.com Funimation.com gamersyde.com gamespot.com gazeta.pl helsinki.fi hotnewhiphop.com lemonde.fr mnet.com motorsport.com MSN.com
# n-tv.de ndr.de NDTV.com NextMedia.com noz.de


# these sites have mixed media. can handle the video in these sites:
# 20min.ch 5min.com archive.org Allocine.fr(added) br.de bt.no  buzzfeed.com condenast.com firstpost.com gameinformer.com gputechconf.com heise.de HotStar.com(some play) lrt.lt natgeo.com
# nbcsports.com  patreon.com
# 9c9media.com(no posts)

#ytdl plays this fine but no video?
#coub.com

#supported but is an audio only site
#acast.com AudioBoom.com audiomack.com bandcamp.com clyp.it democracynow.org? freesound.org hark.com hearthis.at hypem.com libsyn.com mixcloud.com
#Minhateca.com.br(direct mp3)

#
# ytdl also supports these sites:
# myvideo.co.za  ?
#bluegartr.com  (gif)
# behindkink.com   (not sure)
# facebook.com  (need to work capturing only videos)
# features.aol.com  (inconsistent)
# livestream.com (need to work capturing only videos)
# mail.ru inconsistent(need to work capturing only videos)
# miomio.tv(some play but most won't)
# ooyala.com(some play but most won't)
#

#     extractors=[]
#     from youtube_dl.extractor import gen_extractors
#     for ie in gen_extractors():
#         #extractors.append(ie.IE_NAME)
#         try:
#             log("[%s] %s " %(ie.IE_NAME, ie._VALID_URL) )
#         except Exception as e:
#             log( "zz   " + str(e) )

#     extractors.sort()
#     for n in extractors: log("'%s'," %n)

    from urlparse import urlparse
    parsed_uri = urlparse( url )
    domain = '{uri.netloc}'.format(uri=parsed_uri)

    dialog_progress_YTDL = xbmcgui.DialogProgressBG()
    dialog_progress_YTDL.create('YTDL' )
    dialog_progress_YTDL.update(10,'YTDL','Checking link...' )

    try:
        from resources.lib.domains import ydtl_get_playable_url
        stream_url = ydtl_get_playable_url(url)

        if stream_url:
            dialog_progress_YTDL.update(80,'YTDL', 'Playing' )
            listitem = xbmcgui.ListItem(path=stream_url[0])   #plugins play video like this.
            xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)
        else:
            dialog_progress_YTDL.update(40,'YTDL', 'Trying URLResolver' )
            log('YTDL Unable to get playable URL, Trying UrlResolver...' )

            #ytdl seems better than urlresolver for getting the playable url...
            media_url = urlresolver.resolve(url)
            if media_url:
                dialog_progress_YTDL.update(88,'YTDL', 'Playing' )
                #log( '------------------------------------------------urlresolver stream url ' + repr(media_url ))
                listitem = xbmcgui.ListItem(path=media_url)
                xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)
            else:
                log('UrlResolver cannot get a playable url' )
                xbmc.executebuiltin('XBMC.Notification("%s", "%s" )'  %( translation(30192), domain )  )

    except Exception as e:
        xbmc.executebuiltin('XBMC.Notification("%s(YTDL)","%s")' %(  domain, str(e))  )
    finally:
        dialog_progress_YTDL.update(100,'YTDL' ) #not sure if necessary to set to 100 before closing dialogprogressbg
        dialog_progress_YTDL.close()

def listLinksInComment(url, name, type):
    from resources.lib.domains import parse_reddit_link, sitesBase, build_DirectoryItem_url_based_on_media_type
    from resources.lib.utils import markdown_to_bbcode, unescape, ret_info_type_icon, build_script
    #from resources.domains import make_addon_url_from
    #called from context menu
    log('listLinksInComment:%s:%s' %(type,url) )

    #does not work for list comments coz key is the playable url (not reddit comments url)
    #msg=WINDOW.getProperty(url)
    #WINDOW.clearProperty( url )
    #log( '   msg=' + msg )

    directory_items=[]
    author=""
    ShowOnlyCommentsWithlink=False

    if type=='linksOnly':
        ShowOnlyCommentsWithlink=True

    #sometimes the url has a query string. we discard it coz we add .json at the end
    #url=url.split('?', 1)[0]+'.json'

    #url='https://www.reddit.com/r/Music/comments/4k02t1/bonnie_tyler_total_eclipse_of_the_heart_80s_pop/' + '.json'
    #only get up to "https://www.reddit.com/r/Music/comments/4k02t1".
    #   do not include                                            "/bonnie_tyler_total_eclipse_of_the_heart_80s_pop/"
    #   because we'll have problem when it looks like this: "https://www.reddit.com/r/Overwatch/comments/4nx91h/ever_get_that_feeling_dÃ©jÃ _vu/"

    #url=re.findall(r'(.*/comments/[A-Za-z0-9]+)',url)[0]
    url=urllib.quote_plus(url,safe=':/')
    url+='.json'

    content = reddit_request(url)
    if not content: return

    content = json.loads(content)

    del harvest[:]
    #harvest links in the post text (just 1)
    r_linkHunter(content[0]['data']['children'])

    try:submitter=content[0]['data']['children'][0]['data']['author']
    except: submitter=''

    #the post title is provided in json, we'll just use that instead of messages from addLink()
    try:post_title=content[0]['data']['children'][0]['data']['title']
    except:post_title=''
    #for i, h in enumerate(harvest):
    #    log("aaaaa first harvest "+h[2])

    #harvest links in the post itself
    r_linkHunter(content[1]['data']['children'])

    comment_score=0
    for i, h in enumerate(harvest):
        try:
            #log(str(i)+"  score:"+ str(h[0]).zfill(5)+" "+ h[1] +'|'+ h[3] )
            comment_score=h[0]
            #log("score %d < %d (%s)" %(comment_score,int_CommentTreshold, CommentTreshold) )
            link_url=h[2]
            desc100=h[3].replace('\n',' ')[0:100] #first 100 characters of description

            kind=h[6] #reddit uses t1 for user comments and t3 for OP text of the post. like a poster describing the post.
            d=h[5]   #depth of the comment

            tab=" "*d if d>0 else "-"

            from urlparse import urlparse
            domain = '{uri.netloc}'.format( uri=urlparse( link_url ) )

            author=h[7]
            DirectoryItem_url=''

            if comment_score < int_CommentTreshold:
                continue

            #hoster, DirectoryItem_url, videoID, mode_type, thumb_url,poster_url, isFolder,setInfo_type, setProperty_IsPlayable =make_addon_url_from(h[2])
            #if link_url:
            #    log( '  comment %s TITLE:%s... link[%s]' % ( str(d).zfill(3), desc100.ljust(20)[:20],link_url ) )

            ld=parse_reddit_link(link_url=link_url, assume_is_video=False, needs_preview=True, get_playable_url=True )

            if kind=='t1':
                list_title=r"[COLOR cadetblue]%3d[/COLOR] %s" %( h[0], tab )
            elif kind=='t3':
                list_title=r"[COLOR cadetblue]Title [/COLOR] %s" %( tab )

            #helps the the textbox control treat [url description] and (url) as separate words. so that they can be separated into 2 lines
            plot=h[3].replace('](', '] (')
            plot= markdown_to_bbcode(plot)
            plot=unescape(plot)  #convert html entities e.g.:(&#39;)

#            liz=xbmcgui.ListItem(label=     "[COLOR greenyellow]*"+     list_title+"[%s] %s"%(domain, result.replace('\n',' ')[0:100])  + "[/COLOR]",
#                                 label2="",
#                                 iconImage="",
#                                 thumbnailImage='',
#                                 path=DirectoryItem_url)

            liz=xbmcgui.ListItem(label=list_title +': '+ desc100 ,
                                 label2="",
                                 iconImage="",
                                 thumbnailImage="")

            liz.setInfo( type="Video", infoLabels={ "Title": h[1], "plot": plot, "studio": domain, "votes": str(comment_score), "director": author  } )
            isFolder=False

            #force all links to ytdl to see if it can be played
            if link_url:

                DirectoryItem_url, setProperty_IsPlayable, isFolder, title_prefix = build_DirectoryItem_url_based_on_media_type(ld, link_url)

                liz.setProperty('IsPlayable', setProperty_IsPlayable)
                liz.setProperty('url', DirectoryItem_url)  #<-- needed by the xml gui skin
                liz.setPath(DirectoryItem_url)

                if domain:
                    plot= "  [COLOR greenyellow][%s] %s"%(domain, plot )  + "[/COLOR]"
                else:
                    plot= "  [COLOR greenyellow][%s]"%( plot ) + "[/COLOR]"
                liz.setLabel(list_title+plot)

                #log('      there is a link from %s' %domain)
                if ld:
                    liz.setArt({"thumb": ld.poster, "poster":ld.poster, "banner":ld.poster, "fanart":ld.poster, "landscape":ld.poster   })
                #else:
                #    DirectoryItem_url=sys.argv[0]+"?url="+ urllib.quote_plus(link_url) +"&mode=play"

            if DirectoryItem_url:
                log( 'IsPlayable:'+setProperty_IsPlayable )
                directory_items.append( (DirectoryItem_url, liz, isFolder,) )
                #xbmcplugin.addDirectoryItem(handle=pluginhandle,url=DirectoryItem_url,listitem=liz,isFolder=isFolder)
            else:
                #this section are for comments that have no links
                if not ShowOnlyCommentsWithlink:
                    result=h[3].replace('](', '] (')
                    result=markdown_to_bbcode(result)
                    liz=xbmcgui.ListItem(label=list_title + desc100 ,
                                         label2="",
                                         iconImage="",
                                         thumbnailImage="")
                    liz.setInfo( type="Video", infoLabels={ "Title": h[1], "plot": result, "studio": domain, "votes": str(h[0]), "director": author } )
                    liz.setProperty('IsPlayable', 'false')

                    directory_items.append( ("", liz, False,) )
                    #xbmcplugin.addDirectoryItem(handle=pluginhandle,url="",listitem=liz,isFolder=False)

                #END section are for comments that have no links or unsupported links
        except Exception as e:
            log('  EXCEPTION:' + str(e) )

        #for di in directory_items:
        #    log( str(di) )

    log('  comments_view id=%s' %comments_viewMode)

    #xbmcplugin.setContent(pluginhandle, "mixed")  #in estuary, mixed have limited view id's available. it has widelist which is nice for comments but we'll just stick with 'movies'
    xbmcplugin.setContent(pluginhandle, "movies")    #files, songs, artists, albums, movies, tvshows, episodes, musicvideos
    xbmcplugin.setPluginCategory(pluginhandle,'Comments')

    xbmcplugin.addDirectoryItems(handle=pluginhandle, items=directory_items )
    xbmcplugin.endOfDirectory(pluginhandle)

    if comments_viewMode:
        xbmc.executebuiltin('Container.SetViewMode(%s)' %comments_viewMode)


harvest=[]
def r_linkHunter(json_node,d=0):
    #from resources.domains import url_is_supported
    from resources.lib.utils import unescape
    #recursive function to harvest stuff from the reddit comments json reply
    prog = re.compile('<a href=[\'"]?([^\'" >]+)[\'"]>(.*?)</a>')
    for e in json_node:
        link_desc=""
        link_http=""
        author=""
        created_utc=""
        if e['kind']=='t1':     #'t1' for comments   'more' for more comments (not supported)

            #log("replyid:"+str(d)+" "+e['data']['id'])
            body=e['data']['body'].encode('utf-8')

            #log("reply:"+str(d)+" "+body.replace('\n','')[0:80])

            try: replies=e['data']['replies']['data']['children']
            except: replies=""

            try: score=e['data']['score']
            except: score=0

            try: post_text=unescape( e['data']['body'].encode('utf-8') )
            except: post_text=""
            post_text=post_text.replace("\n\n","\n")

            try: post_html=unescape( e['data']['body_html'].encode('utf-8') )
            except: post_html=""

            try: created_utc=e['data']['created_utc']
            except: created_utc=""

            try: author=e['data']['author'].encode('utf-8')
            except: author=""

            #i initially tried to search for [link description](https:www.yhotuve.com/...) in the post_text but some posts do not follow this convention
            #prog = re.compile('\[(.*?)\]\((https?:\/\/.*?)\)')
            #result = prog.findall(post_text)

            result = prog.findall(post_html)
            if result:
                #store the post by itself and then a separate one for each link.
                harvest.append((score, link_desc, link_http, post_text, post_html, d, "t1",author,created_utc,)   )

                for link_http,link_desc in result:
                    #if url_is_supported(link_http) :
                        #store an entry for every supported link.
                    harvest.append((score, link_desc, link_http, link_desc, post_html, d, "t1",author,created_utc,)   )
            else:
                harvest.append((score, link_desc, link_http, post_text, post_html, d, "t1",author,created_utc,)   )

            d+=1 #d tells us how deep is the comment in
            r_linkHunter(replies,d)
            d-=1

        if e['kind']=='t3':     #'t3' for post text (a description of the post)
            #log(str(e))
            #log("replyid:"+str(d)+" "+e['data']['id'])
            try: score=e['data']['score']
            except: score=0

            try: self_text=unescape( e['data']['selftext'].encode('utf-8') )
            except: self_text=""

            try: self_text_html=unescape( e['data']['selftext_html'].encode('utf-8') )
            except: self_text_html=""

            result = prog.findall(self_text_html)
            if len(result) > 0 :
                harvest.append((score, link_desc, link_http, self_text, self_text_html, d, "t3",author,created_utc, )   )

                for link_http,link_desc in result:
                    #if url_is_supported(link_http) :
                    harvest.append((score, link_desc, link_http, link_desc, self_text_html, d, "t3",author,created_utc, )   )
            else:
                if len(self_text) > 0: #don't post an empty titles
                    harvest.append((score, link_desc, link_http, self_text, self_text_html, d, "t3",author,created_utc,)   )

#This handles the links sent via jsonrpc (i.e.: links sent by kore to kodi by calling)
# videoUrl = "plugin://script.reddit.reader/?mode=play&url=" + URLEncoder.encode(videoUri.toString(), "UTF-8");
def parse_url_and_play(url, name, type):
    from resources.lib.domains import parse_reddit_link, sitesBase, ydtl_get_playable_url, build_DirectoryItem_url_based_on_media_type
    from resources.lib.domains import viewImage
    isFolder=False

    log('parse_url_and_play url='+url)
    #log('pluginhandle='+str(pluginhandle) )
    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    ld=parse_reddit_link(url,True, False, False  )

    DirectoryItem_url, setProperty_IsPlayable, isFolder, title_prefix = build_DirectoryItem_url_based_on_media_type(ld, url)



    if setProperty_IsPlayable=='true':
        log( '---------IsPlayable---------->'+ DirectoryItem_url)
        playVideo(DirectoryItem_url,'','')
    else:
        if isFolder: #showing album
            log( '---------using ActivateWindow------>'+ DirectoryItem_url)
            xbmc.executebuiltin('ActivateWindow(Videos,'+ DirectoryItem_url+')')
        else:  #viewing image
            log( '---------using setResolvedUrl------>'+ DirectoryItem_url)
            #viewImage(DirectoryItem_url,'','' )

            #error message after picture is displayed, kore remote will be unresponsive
            #playVideo(DirectoryItem_url,'','')

            #endless loop. picture windowxml opens after closing, opens again after closing....
            #xbmc.executebuiltin('ActivateWindow(Videos,'+ DirectoryItem_url+')')

            #log( 'Container.Update(%s?path=%s?prl=zaza&mode=viewImage&url=%s)' % ( sys.argv[0], sys.argv[0], urllib.quote_plus(url) )  )
            #xbmc.executebuiltin('Container.Update(%s?path=%s?prl=zaza&mode=viewImage&url=%s)' % ( sys.argv[0], sys.argv[0], urllib.quote_plus(url) ) )

            listitem = xbmcgui.ListItem(path='')
            listitem.setProperty('IsPlayable', 'false')
            xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)

            #DirectoryItem_url=DirectoryItem_url.replace('plugin://', 'script://')
            #xbmc.executebuiltin('RunScript(script.reddit.reader)' )
            #xbmc.executebuiltin('RunScript(script.reddit.reader,mode=viewImage&url=%s)' %urllib.quote_plus(url) )
            #xbmc.executebuiltin('RunPlugin(%s?path=%s?prl=zaza&mode=viewImage&url=%s)' % ( sys.argv[0], sys.argv[0], urllib.quote_plus(url) ) )
            xbmc.executebuiltin('RunPlugin(%s)' % ( DirectoryItem_url ) )





        #listitem = xbmcgui.ListItem(path=DirectoryItem_url)
        #listitem.setProperty('IsPlayable', setProperty_IsPlayable)
        #xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)

        #xbmc.executebuiltin('RunPlugin(%s)' %DirectoryItem_url)
        #xbmc.executebuiltin('ActivateWindow(Videos,'+ DirectoryItem_url+')')

#    if ld:
#        if setProperty_IsPlayable=='true':
#            playVideo(DirectoryItem_url,'','')
#        else:
#            listitem = xbmcgui.ListItem(path=DirectoryItem_url)
#            listitem.setProperty('IsPlayable', setProperty_IsPlayable)
#            xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)
#
#
#
#    else:
#        playable_url = ydtl_get_playable_url( url )  #<-- will return a playable_url or a list of playable urls
#        #playable_url= '(worked)' + title.ljust(15)[:15] + '... '+ w_url
#        #work
#        if playable_url:
#            if pluginhandle>0:
#                for u in playable_url:
#                    listitem = xbmcgui.ListItem(path=u, label=name)   #plugins play video like this.
#                    xbmcplugin.setResolvedUrl(pluginhandle, True, listitem)
#            else:
#                #log('pluginhandleXXXX name=')
#                #this portion won't work with autoplay (playlist)
#                playlist.clear()
#                if len(playable_url)>1: log('    link has multiple videos'  )
#
#                for u in playable_url:
#                    #self.queue.put( [title, u] )
#                    queueVideo(u, name, type)
#                xbmc.Player().play(playlist)
#        else:
#            xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( translation(30192), 'Youtube_dl')  )


#MODE queueVideo       -type not used
def queueVideo(url, name, type):
    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    listitem = xbmcgui.ListItem(name)
    playlist.add(url, listitem)

#searchReddits      --url, name, type not used
def searchReddits(url, name, type):
    keyboard = xbmc.Keyboard('sort=new&t=week&q=', translation(30005))
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():

        #search_string = urllib.quote_plus(keyboard.getText().replace(" ", "+"))
        search_string = keyboard.getText().replace(" ", "+")

        url = urlMain +"/search.json?" +search_string    #+ '+' + nsfw  # + sites_filter skip the sites filter

        listSubReddit(url, name, "")


def translation(id):
    return addon.getLocalizedString(id).encode('utf-8')

def parameters_string_to_dict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict

# def addFavLink(name, url, mode, iconimage, description, date, site, subreddit):
#     ok = True
#     liz = xbmcgui.ListItem(name, iconImage="DefaultVideo.png", thumbnailImage=iconimage)
#     liz.setInfo(type="Video", infoLabels={"Title": name, "Plot": description, "Aired": date})
#     liz.setProperty('IsPlayable', 'true')
#     entries = []
#     entries.append((translation(30018), 'RunPlugin(plugin://'+addonID+'/?mode=queueVideo&url='+urllib.quote_plus(url)+'&name='+urllib.quote_plus(name)+')',))
#     favEntry = '<favourite name="'+name+'" url="'+url+'" description="'+description+'" thumb="'+iconimage+'" date="'+date+'" site="'+site+'" />'
#     entries.append((translation(30024), 'RunPlugin(plugin://'+addonID+'/?mode=removeFromFavs&url='+urllib.quote_plus(favEntry)+'&type='+urllib.quote_plus(subreddit)+')',))
#     if showBrowser and (osWin or osOsx or osLinux):
#         if osWin and browser_win==0:
#             entries.append((translation(30021), 'RunPlugin(plugin://plugin.program.webbrowser/?url='+urllib.quote_plus(site)+'&mode=showSite&zoom='+browser_wb_zoom+'&stopPlayback=no&showPopups=no&showScrollbar=no)',))
#         else:
#             entries.append((translation(30021), 'RunPlugin(plugin://plugin.program.chrome.launcher/?url='+urllib.quote_plus(site)+'&mode=showSite)',))
#     liz.addContextMenuItems(entries)
#     ok = xbmcplugin.addDirectoryItem(handle=pluginhandle, url=url, listitem=liz)
#     return ok

#addDir(subreddit, subreddit.lower(), next_mode, "")
def addDir(name, url, mode, iconimage, type="", listitem_infolabel=None, label2=""):
    #adds a list entry
    u = sys.argv[0]+"?url="+urllib.quote_plus(url)+"&mode="+str(mode)+"&type="+str(type)
    #log('addDir='+u)
    ok = True
    liz = xbmcgui.ListItem(label=name, label2=label2, iconImage="", thumbnailImage='')

    if listitem_infolabel==None:
        liz.setInfo(type="Video", infoLabels={"Title": name})
    else:
        liz.setInfo(type="Video", infoLabels=listitem_infolabel)


    ok = xbmcplugin.addDirectoryItem(handle=pluginhandle, url=u, listitem=liz, isFolder=True)
    return ok

def addDirR(name, url, mode, icon_image='', type="", listitem_infolabel=None, file_entry="", banner_image=''):

    #addDir with a remove subreddit context menu
    #alias is the text for the listitem that is presented to the user
    #file_entryis the actual string(containing alias & viewid) that is saved in the "subreddit" file

    u = sys.argv[0]+"?url="+urllib.quote_plus(url)+"&mode="+str(mode)+"&type="+str(type)
    #log('addDirR='+u)
    ok = True
    liz = xbmcgui.ListItem(name)

    if icon_image:
        liz.setArt({ 'thumb': icon_image, 'icon': icon_image, 'clearlogo': icon_image  })  #thumb is used in 'shift' view (estuary)   thunb,icon are interchangeable in list view

    if banner_image:
        liz.setArt({ 'banner': banner_image  })
        #liz.setArt({ 'poster': banner_image  })
        liz.setArt({ 'fanart': banner_image  })
        #liz.setArt({ 'landscape': banner_image  })

    if listitem_infolabel==None:
        #liz.setInfo(type="Video", infoLabels={"Title": name})
        liz.setInfo(type="Video", infoLabels={"Title": name})
    else:
        liz.setInfo(type="Video", infoLabels=listitem_infolabel)

    if file_entry:
        liz.setProperty("file_entry", file_entry)

    #liz.addContextMenuItems([(translation(30002), 'RunPlugin(plugin://'+addonID+'/?mode=removeSubreddit&url='+urllib.quote_plus(url)+')',)])
    liz.addContextMenuItems([(translation(30003), 'RunPlugin(plugin://'+addonID+'/?mode=editSubreddit&url='+urllib.quote_plus(file_entry)+')',)     ,
                             (translation(30002), 'RunPlugin(plugin://'+addonID+'/?mode=removeSubreddit&url='+urllib.quote_plus(file_entry)+')',)
                             ])

    #log("handle="+sys.argv[1]+" url="+u+" ")
    ok = xbmcplugin.addDirectoryItem(handle=pluginhandle, url=u, listitem=liz, isFolder=True)
    return ok

def reddit_request( url ):
    #log( "  reddit_request " + url )

    #if there is a refresh_token, we use oauth.reddit.com instead of www.reddit.com
    if reddit_refresh_token:
        url=url.replace('www.reddit.com','oauth.reddit.com' )
        log( "  replaced reqst." + url + " + access token=" + reddit_access_token)

    req = urllib2.Request(url)

    #req.add_header('User-Agent', 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.14) Gecko/20080404 Firefox/2.0.0.14')
    req.add_header('User-Agent', reddit_userAgent)   #userAgent = "XBMC:"+addonID+":v"+addon.getAddonInfo('version')+" (by /u/gsonide)"

    #if there is a refresh_token, add the access token to the header
    if reddit_refresh_token:
        req.add_header('Authorization','bearer '+ reddit_access_token )

    try:
        page = urllib2.urlopen(req)
        response=page.read();page.close()
        #log( response )
        return response

    except urllib2.HTTPError, err:
        if err.code in [403,401]:  #401 Unauthorized, 403 forbidden. access tokens expire in 1 hour. maybe we just need to refresh it
            log("    attempting to get new access token")
            if reddit_get_access_token():
                log("      Success: new access token "+ reddit_access_token)
                req.add_header('Authorization','bearer '+ reddit_access_token )
                try:

                    log("      2nd attempt:"+ url)
                    page = urllib2.urlopen(req)   #it has to be https:// not http://
                    response=page.read();page.close()
                    return response

                except urllib2.HTTPError, err:
                    xbmc.executebuiltin('XBMC.Notification("%s %s", "%s" )' %( err.code, err.msg, url)  )
                    log( err.msg )
                except urllib2.URLError, err:
                    log( err.msg )
            else:
                log( "*** failed to get new access token - don't know what to do " )


        xbmc.executebuiltin('XBMC.Notification("%s %s", "%s" )' %( err.code, err.msg, url)  )
        log( err.reason )
    except urllib2.URLError, err: # Not an HTTP-specific error (e.g. connection refused)
        xbmc.executebuiltin('XBMC.Notification("%s", "%s" )' %( err.msg, url)  )
        log( err.msg )


def reddit_get_refresh_token(url, name, type):
    #this function gets a refresh_token from reddit and keep it in our addon. this refresh_token is used to get 1-hour access tokens.
    #  getting a refresh_token is a one-time step

    #1st: use any webbrowser to
    #  https://www.reddit.com/api/v1/authorize?client_id=hXEx62LGqxLj8w&response_type=code&state=RS&redirect_uri=http://localhost:8090/&duration=permanent&scope=read,mysubreddits
    #2nd: click allow and copy the code provided after reddit redirects the user
    #  save this code in add-on settings.  A one-time use code that may be exchanged for a bearer token.
    code = addon.getSetting("reddit_code")

    if reddit_refresh_token and code:
        dialog = xbmcgui.Dialog()
        if dialog.yesno("Replace reddit refresh token", "You already have a refresh token.", "You only need to get this once.", "Are you sure you want to replace it?" ):
            pass
        else:
            return

    try:
        log( "Requesting a reddit permanent token with code=" + code )

        req = urllib2.Request('https://www.reddit.com/api/v1/access_token')

        #http://stackoverflow.com/questions/6348499/making-a-post-call-instead-of-get-using-urllib2
        data = urllib.urlencode({'grant_type'  : 'authorization_code'
                                ,'code'        : code                     #'woX9CDSuw7XBg1MiDUnTXXQd0e4'
                                ,'redirect_uri': reddit_redirect_uri})    #http://localhost:8090/

        #http://stackoverflow.com/questions/2407126/python-urllib2-basic-auth-problem
        import base64
        base64string = base64.encodestring('%s:%s' % (reddit_clientID, '')).replace('\n', '')
        req.add_header('Authorization',"Basic %s" % base64string)
        req.add_header('User-Agent', reddit_userAgent)

        page = urllib2.urlopen(req, data=data)
        response=page.read();page.close()
        log( response )

        #response='{"access_token": "xmOMpbJc9RWqjPS46FPcgyD_CKc", "token_type": "bearer", "expires_in": 3600, "refresh_token": "56706164-ZZiEqtAhahg9BkpINvrBPQJhZL4", "scope": "identity read"}'
        status=reddit_set_addon_setting_from_response(response)

        if status=='ok':
            r1="Click 'OK' when done"
            r2="Settings will not be saved"
            xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( r1, r2)  )
        else:
            r2="Requesting a reddit permanent token"
            xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( status, r2)  )


#    This is a 2nd option reddit oauth. user needs to request access token every hour
#         #user enters this on their webbrowser. note that there is no duration=permanent response_type=token instead of code
#         request_url='https://www.reddit.com/api/v1/authorize?client_id=hXEx62LGqxLj8w&response_type=token&state=RS&redirect_uri=http://localhost:8090/&scope=read,identity'
#         #click on "Allow"
#         #copy the redirect url code    #enters it on settings. e.g.: LVQu8vitbEXfMPcK1sGlVVQZEpM
#
#         #u='https://oauth.reddit.com/new.json'
#         u='https://oauth.reddit.com//api/v1/me.json'
#
#         req = urllib2.Request(u)
#         #req.add_header('User-Agent', 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.8.1.14) Gecko/20080404 Firefox/2.0.0.14')
#         req.add_header('User-Agent', reddit_userAgent)
#         req.add_header('Authorization','bearer LVQu8vitbEXfMPcK1sGlVVQZEpM')
#         page = read,identity.urlopen(req)
#         response=page.read();page.close()

    except urllib2.HTTPError, err:
        xbmc.executebuiltin('XBMC.Notification("%s %s", "%s" )' %( err.code, err.msg, u)  )
        log( err.reason )
    except urllib2.URLError, err: # Not an HTTP-specific error (e.g. connection refused)
        log( err.reason )

def reddit_get_access_token(url="", name="", type=""):
    try:
        log( "Requesting a reddit 1-hour token" )

        req = urllib2.Request('https://www.reddit.com/api/v1/access_token')

        #http://stackoverflow.com/questions/6348499/making-a-post-call-instead-of-get-using-urllib2
        data = urllib.urlencode({'grant_type'    : 'refresh_token'
                                ,'refresh_token' : reddit_refresh_token })                    #'woX9CDSuw7XBg1MiDUnTXXQd0e4'

        #http://stackoverflow.com/questions/2407126/python-urllib2-basic-auth-problem
        import base64
        base64string = base64.encodestring('%s:%s' % (reddit_clientID, '')).replace('\n', '')
        req.add_header('Authorization',"Basic %s" % base64string)
        req.add_header('User-Agent', reddit_userAgent)

        page = urllib2.urlopen(req, data=data)
        response=page.read();page.close()
        #log( response )

        #response='{"access_token": "lZN8p1QABSr7iJlfPjIW0-4vBLM", "token_type": "bearer", "device_id": "None", "expires_in": 3600, "scope": "identity read"}'
        status=reddit_set_addon_setting_from_response(response)

        if status=='ok':
            #log( '    ok new access token '+ reddit_access_token )
            #r1="Click 'OK' when done"
            #r2="Settings will not be saved"
            #xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( r1, r2)  )
            return True
        else:
            r2="Requesting 1-hour token"
            xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( status, r2)  )

    except urllib2.HTTPError, err:
        xbmc.executebuiltin('XBMC.Notification("%s %s", "%s" )' %( err.code, err.msg, req.get_full_url())  )
        log( err.reason )
    except urllib2.URLError, err: # Not an HTTP-specific error (e.g. connection refused)
        log( err.reason )

    return False

def reddit_set_addon_setting_from_response(response):
    from resources.lib.utils import convert_date
    global reddit_access_token    #specify "global" if you wanto to change the value of a global variable
    global reddit_refresh_token
    try:
        response = json.loads(response.replace('\\"', '\''))
        log( json.dumps(response, indent=4) )

        if 'error' in response:
            #Error                      Cause                                                                Resolution
            #401 response               Client credentials sent as HTTP Basic Authorization were invalid     Verify that you are properly sending HTTP Basic Authorization headers and that your credentials are correct
            #unsupported_grant_type     grant_type parameter was invalid or Http Content type was not set correctly     Verify that the grant_type sent is supported and make sure the content type of the http message is set to application/x-www-form-urlencoded
            #NO_TEXT for field code     You didn't include the code parameter                                Include the code parameter in the POST data
            #invalid_grant              The code has expired or already been used                            Ensure that you are not attempting to re-use old codes - they are one time use.
            return response['error']
        else:
            if 'refresh_token' in response:  #refresh_token only returned when getting reddit_get_refresh_token. it is a one-time step
                reddit_refresh_token = response['refresh_token']
                addon.setSetting('reddit_refresh_token', reddit_refresh_token)

            reddit_access_token = response['access_token']
            addon.setSetting('reddit_access_token', reddit_access_token)
            #log( '    new access token '+ reddit_access_token )

            addon.setSetting('reddit_access_token_scope', response['scope'])

            unix_time_now = int(time.time())
            unix_time_now += int( response['expires_in'] )
            addon.setSetting('reddit_access_token_expires', convert_date(unix_time_now))

    except Exception as e:
        log("  parsing reddit token response EXCEPTION:="+ str( sys.exc_info()[0]) + "  " + str(e) )
        return str(e)

    return "ok"

def reddit_revoke_refresh_token(url, name, type):
    global reddit_access_token    #specify "global" if you wanto to change the value of a global variable
    global reddit_refresh_token
    try:
        log( "Revoking refresh token " )

        req = urllib2.Request('https://www.reddit.com/api/v1/revoke_token')

        data = urllib.urlencode({'token'          : reddit_refresh_token
                                ,'token_type_hint': 'refresh_token'       })

        import base64
        base64string = base64.encodestring('%s:%s' % (reddit_clientID, '')).replace('\n', '')
        req.add_header('Authorization',"Basic %s" % base64string)
        req.add_header('User-Agent', reddit_userAgent)

        page = urllib2.urlopen(req, data=data)
        response=page.read();page.close()

        #no response for success.
        log( "response:" + response )

        #response = json.loads(response.replace('\\"', '\''))
        #log( json.dumps(response, indent=4) )

        addon.setSetting('reddit_refresh_token', "")
        addon.setSetting('reddit_access_token', "")
        addon.setSetting('reddit_access_token_scope', "")
        addon.setSetting('reddit_access_token_expires', "")
        reddit_refresh_token=""
        reddit_access_token=""

        r2="Revoking refresh token"
        xbmc.executebuiltin("XBMC.Notification(%s, %s)"  %( 'Token revoked', r2)  )

    except urllib2.HTTPError, err:
        xbmc.executebuiltin('XBMC.Notification("%s %s", "%s" )' %( err.code, err.msg, req.get_full_url() )  )
        log( "http error:" + err.reason )
    except Exception as e:
        xbmc.executebuiltin('XBMC.Notification("%s", "%s" )' %( str(e), 'Revoking refresh token' )  )
        log("  Revoking refresh token EXCEPTION:="+ str( sys.exc_info()[0]) + "  " + str(e) )


DATEFORMAT = xbmc.getRegion('dateshort')
TIMEFORMAT = xbmc.getRegion('meridiem')

def xbmc_busy(busy=True):
    if busy:
        xbmc.executebuiltin("ActivateWindow(busydialog)")
    else:
        xbmc.executebuiltin( "Dialog.Close(busydialog)" )

def log(message, level=xbmc.LOGNOTICE):
    xbmc.log("reddit_viewer:"+message, level=level)

if __name__ == '__main__':
    dbPath = getDbPath()
    if dbPath:
        conn = sqlite3.connect(dbPath)
        c = conn.cursor()



    params = parameters_string_to_dict(sys.argv[2])
    mode   = urllib.unquote_plus(params.get('mode', ''))
    url    = urllib.unquote_plus(params.get('url', ''))
    typez  = urllib.unquote_plus(params.get('type', '')) #type is a python function, try not to use a variable name same as function
    name   = urllib.unquote_plus(params.get('name', ''))
    #xbmc supplies this additional parameter if our <provides> in addon.xml has more than one entry e.g.: <provides>video image</provides>
    #xbmc only does when the add-on is started. we have to pass it along on subsequent calls
    # if our plugin is called as a pictures add-on, value is 'image'. 'video' for video
    #content_type=urllib.unquote_plus(params.get('content_type', ''))
    #ctp = "&content_type="+content_type   #for the lazy
    #log("content_type:"+content_type)

    if HideImagePostsOnVideo: # and content_type=='video':
        setting_hide_images=True
    #log("HideImagePostsOnVideo:"+str(HideImagePostsOnVideo)+"  setting_hide_images:"+str(setting_hide_images))
    # log("params="+sys.argv[2]+"  ")

    log( "----------------v" + addon.getAddonInfo('version')  + ' ' + ( mode+': '+url if mode else '' ) +'-----------------')
#    log( repr(sys.argv))
#    log("----------------------")
#    log("params="+ str(params))
#    log("mode="+ mode)
#    log("type="+ typez)
#    log("name="+ name)
#    log("url="+  url)
#    log("pluginhandle:" + str(pluginhandle) )
#    log("-----------------------")

    from resources.lib.domains import viewImage, listAlbum, viewTallImage, playURLRVideo, loopedPlayback
    from resources.lib.slideshow import autoSlideshow
    from resources.lib.converthtml import readHTML

    if mode=='':mode='index'  #default mode is to list start page (index)
    #plugin_modes holds the mode string and the function that will be called given the mode
    plugin_modes = {'index'                 : index
                    ,'listSubReddit'        : listSubReddit
                    ,'playVideo'            : playVideo
                    ,'addSubreddit'         : addSubreddit
                    ,'editSubreddit'        : editSubreddit
                    ,'removeSubreddit'      : removeSubreddit
                    ,'autoPlay'             : autoPlay
                    ,'viewImage'            : viewImage
                    ,'viewTallImage'        : viewTallImage
                    ,'listAlbum'            : listAlbum
#                    ,'queueVideo'           : queueVideo
#                    ,'addToFavs'            : addToFavs
#                    ,'removeFromFavs'       : removeFromFavs
#                    ,'searchReddits'        : searchReddits
#                    ,'openSettings'         : openSettings
                    ,'listLinksInComment'   : listLinksInComment
                    ,'playYTDLVideo'        : playYTDLVideo
                    ,'playURLRVideo'        : playURLRVideo
                    ,'loopedPlayback'       : loopedPlayback
#                    ,'playVidmeVideo'       : playVidmeVideo
#                    ,'listTumblrAlbum'      : listTumblrAlbum
#                    ,'playStreamable'       : playStreamable
#                    ,'playInstagram'        : playInstagram
#                    ,'playFlickr'           : playFlickr
#                    ,'listFlickrAlbum'      : playFlickr
                    ,'get_refresh_token'    : reddit_get_refresh_token
                    ,'get_access_token'     : reddit_get_access_token
                    ,'revoke_refresh_token' : reddit_revoke_refresh_token
                    ,'play'                 : parse_url_and_play
                    }
    #whenever a list item is clicked, this part handles it.
    plugin_modes[mode](url,name,typez)

#    usually this plugin is called by a list item constructed like the one below
#         u = sys.argv[0]+"?url=&mode=addSubreddit&type="   #these are the arguments that is sent to our plugin and processed by plugin_modes
#         liz = xbmcgui.ListItem("Add Subreddit",label2="aaa", iconImage="DefaultFolder.png", thumbnailImage="")
#         liz.setInfo(type="Video", infoLabels={"Title": "aaaaaaa", "Plot": "description", "Aired": "daate", "mpaa": "aa"})
#         xbmcplugin.addDirectoryItem(handle=pluginhandle, url=u, listitem=liz, isFolder=True)



'''
github notes:  (6-27-2016)

# Clone your fork of kodi's repo into the current directory in terminal
git clone git@github.com:gedisony/repo-plugins.git repo-plugins

# Navigate to the newly cloned directory
cd repo-plugins

# Assign the original repo to a remote called "upstream"
git remote add upstream https://github.com/xbmc/repo-plugins.git

#
git checkout jarvis


If you cloned a while ago, get the latest changes from upstream:

# Fetch upstream changes
git fetch upstream
# Make sure you are on your 'master' branch
git checkout master
# Merge upstream changes
git merge upstream/master

'master' is only used as example here. Please replace it with the correct branch you want to submit your add-on towards.
*** i think you need to use 'origin/jarvis' instead of 'master'



#Create a new branch to contain your new add-on or subsequent update:
git checkout -b <add-on-branch-name>                       <------while testing, i ended up naming the branch name as "add-on-branch-name"
#The branch name isn't really relevant however a good suggestion is to name it like the addon ID.


#Commit your changes in a single commit, or your pull request is unlikely to be merged into the main repository.
#Use git's interactive rebase feature to tidy up your commits before making them public. The commit for your add-on should have the following naming convention as the following example:
*** don't know what it means "single commit" (how to commit?)
*** go to repo-plugins and copy the entire folder plugin.video.reddit_viewer-master
*** remove the "-master"  --> plugin.video.reddit_viewer
***
*** this is what i did:
$ git commit -m "[plugin.video.reddit_viewer] 2.7.1"
On branch add-on-branch-name
Untracked files:
        plugin.video.reddit_viewer/                <------ error message

nothing added to commit but untracked files present

edipc@DESKTOP-5C55U1P MINGW64 ~/kodi stuff/repo-plugins (add-on-branch-name)
$ git add .    <---- did this to fix the error.

$ git commit -m "[plugin.video.reddit_viewer] 2.7.1"  <------- this will now work


#Push your topic branch up to your fork:

git push origin add-on-branch-name

#Open a pull request with a clear title and description.

*** on browser: click on pull request
upper left : base fork: xbmc/repo-plugins         base:    jarvis
upper right: head fork: gedisony/repo-plugins     compare: add-on-branch-name
*** the clear title till be [plugin.video.reddit_viewer] 2.7.1
*** (don't know what description) left it as blank

*** sent pull request on 6/27/2016

'''
'''
new github notes (7/1/2016) special thanks to Skipmode A1  http://forum.kodi.tv/showthread.php?tid=280882&pid=2365444#pid2365444

rem For a total restart: Delete repo-plugins from your repo on Github
rem For a total restart: Fork the official kodi repo to your repo on Github
rem Deleting C:\Kodi_stuff\repo-plugins and Cloning the kodi repo from your github to your pc
rem Ctrl-C to abort!!!!
pause
rmdir /s /q C:\Kodi_stuff\repo-plugins
cd C:\Kodi_stuff\
c:
rem Cloning the kodi repo from your github to your pc
git clone git@github.com:gedisony/repo-plugins.git repo-plugins
cd C:\Kodi_stuff\repo-plugins

rem Assign the official kodi repo to a remote called "upstream"
git remote add upstream https://github.com/xbmc/repo-plugins.git

rem Add the addon in your github as a remote
git remote add plugin.video.reddit_viewer git@github.com:gedisony/plugin.video.reddit_viewer

rem Fetch your addon from your github
git fetch plugin.video.reddit_viewer

rem Make a branch for your addon and go to that branch
git checkout -b branch_2.7.2 plugin.video.reddit_viewer/master

rem go to the jarvis branch
git checkout jarvis

rem delete the old version of the addon
git rm .\%1\ -r

rem get the new version of the addon from the branch you created
git read-tree --prefix=plugin.video.reddit_viewer/ -u branch_2.7.2

rem force remove .git files (not used for me)
git rm -f C:\Kodi_stuff\repo-plugins\plugin.video.reddit_viewer\.gitattributes
git rm -f C:\Kodi_stuff\repo-plugins\plugin.video.reddit_viewer\.gitignore

rem show the differences
git diff --staged

rem Commit the changes
Git commit -m "[plugin.video.reddit_viewer] 2.7.2"

rem push the stuff to the jarvis branch in your github (if everything went ok):
git push origin jarvis

*** on browser: click on pull request (similar to one above)
'''