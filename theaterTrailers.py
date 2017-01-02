#!/usr/bin/python

from __future__ import unicode_literals
from datetime import datetime
import youtube_dl
import tmdbsimple as tmdb
import logging
import json
import shutil
import re
import os
import time
import requests

#Local Modules
from ConfigMapper.configMapper import ConfigSectionMap


# Global items
MovieDict = {}
MovieList = []
DirsDict = {}
ResultsDict = {}
search = tmdb.Search()

# Sets the directory TheaterTrailers is running from
TheaterTrailersHome = os.path.dirname(os.path.realpath(__file__))

# Sets the location of the trailers.conf file
configfile = os.path.join(TheaterTrailersHome, 'Config', 'trailers.conf')

# Config Variables
tmdb.API_KEY = ConfigSectionMap("main", configfile)['tmdb_api_key']
playlistEndVar = int(ConfigSectionMap("main", configfile)['playlistendvar'])
youtubePlaylist = ConfigSectionMap("main", configfile)['youtubeplaylist']
runCleanup = ConfigSectionMap("main", configfile)['runcleanup']
if ConfigSectionMap("main", configfile)['trailerlocation'] == "":
  trailerLocation = os.path.join(TheaterTrailersHome, 'Trailers')
else:
  trailerLocation = ConfigSectionMap("main", configfile)['trailerlocation']
redBand = ConfigSectionMap("main", configfile)['redband']
plexHost = ConfigSectionMap("main", configfile)['plexhost']
plexPort = ConfigSectionMap("main", configfile)['plexport']
plexToken = ConfigSectionMap("main", configfile)['plextoken']
loggingLevel = ConfigSectionMap("main", configfile)['logginglevel']
couchPotatoHost = ConfigSectionMap("main", configfile)['couchpotatohost']
couchPotatoPort = ConfigSectionMap("main", configfile)['couchpotatoport']
couchPotatoKey = ConfigSectionMap("main", configfile)['couchpotatokey']
pushToCP = ConfigSectionMap("main", configfile)['pushtocp']
pullFromCp = ConfigSectionMap("main", configfile)['pullfromcp']
couchPotatoURI = ConfigSectionMap("main", configfile)['couchpotatouri']
cacheRefresh = int(ConfigSectionMap("main", configfile)['cacherefresh'])
cacheDir = os.path.join(TheaterTrailersHome, "Cache")
if not os.path.exists(cacheDir):
  os.makedirs(cacheDir)
if not os.path.isfile(os.path.join(cacheDir, 'theaterTrailersCache.json')):
  open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'w').close()

# Pause in seconds. TMDB has a rate limit of 40 requests per 10 seconds
pauseRate = .25

# Logging options
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
if not os.path.isdir(os.path.join(TheaterTrailersHome, 'Logs')):
  os.makedirs(os.path.join(TheaterTrailersHome, 'Logs'))
if os.path.isfile(os.path.join(TheaterTrailersHome, 'theaterTrailers.log')):
  shutil.move(os.path.join(TheaterTrailersHome, 'theaterTrailers.log'), os.path.join(TheaterTrailersHome, 'Logs', 'theaterTrailers.log')) 
fh = logging.FileHandler(os.path.join(TheaterTrailersHome, 'Logs', 'theaterTrailers.log'))
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Sets the Current Date in ISO format
currentDate = time.strftime('%Y-%m-%d')


# Main detirmines the flow of the module
def main():

  if runCleanup == 'True':
    cleanup()

  checkCashe()

  infoDownloader(youtubePlaylist)
  
  # Querries tmdb and updates the release date in the dictionary
  for item in MovieList:
    try:
      if MovieDict['item']['Release Date'] in MovieDict:
        continue
    except KeyError as ke1:
      with open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'r+') as fp:
        try:
          DB_Dict = json.load(fp)
          MovieDict[item]['Release Date'] = DB_Dict[keymaker(item)]['Release Date']

        except (KeyError, ValueError) as e:
          tmdbInfo(item)
          tempList = search.results
          tempList.reverse()
          for s in tempList:
            releaseDate = s['release_date']
            releaseDateList = releaseDate.split('-')
            try:
              if (int(releaseDateList[0]) - 1) <= int(MovieDict[item]['Trailer Release']) <= (int(releaseDateList[0]) + 1):
                MovieDict[item]['Release Date'] = releaseDate
            except ValueError as e:
              logger.error("ValueError {0}".format(e))
              pass

        except AttributeError as ae1:
          logger.error("AttributeError {0}".format(item))
          continue

    # Adds the movies to the cache
    title = item.strip()
    try:
      yearVar = MovieDict[item]['Release Date'].split('-')
      trailerYear = yearVar[0].strip()
      updateCache(MovieDict[item]['url'], title, trailerYear)
    except KeyError as error:
      logger.warning("{0} is missing its release date".format(item))
    

def getImdbID(title, year):
  r = requests.get('http://www.omdbapi.com/?t={0}&y={1}&plot=short&r=json'.format(title, year))
  if r.status_code != 200:
    logger.warning("Could not reach the omdbapi correctly")
  else:
    data = json.loads(r.text)
    return data["imdbID"]


def addToCouchPotato(imdbKey):
  if couchPotatoKey == "" or couchPotatoHost == "" or couchPotatoPort == "":
    return
  elif pushToCP == False:
    return
  else:
    r = requests.get('http://{0}:{1}/{2}api/{3}/movie.add/?identifier="{4}"'.format(couchPotatoHost, couchPotatoPort, couchPotatoURI, couchPotatoKey, imdbKey))


def checkCashe():
    if os.path.exists(cacheDir):
      if os.path.isfile(os.path.join(cacheDir, 'theaterTrailersCache.json')):
        with open(os.path.join(cacheDir, 'theaterTrailersCache.json')) as fp:
          try:
            cacheDict = json.load(fp)
            creationDate = datetime.strptime(cacheDict['Creation Date'] , '%Y-%m-%d').date()
            Current_Date = datetime.strptime(currentDate, '%Y-%m-%d').date()
            age = Current_Date - creationDate
            age = age.days
            logger.info('The cache is {0} days old'.format(age))
            if(age==cacheRefresh):
              os.remove(os.path.join(cacheDir, 'theaterTrailersCache.json'))

          except ValueError as e:
            logger.info("ValueError {0}".format(e))
            logger.info("Cache file empty")

    else:
      logger.info("making cache dir")
      os.makedirs(cacheDir)


def checkDownloadDate(passedTitle):
  try:
    if currentDate < MovieDict[passedTitle]['Release Date']:
      return True
  except KeyError as ke2:
    logger.error("KeyError {0}".format(ke2))
    logger.error(MovieDict[passedTitle] + " has no release date")

def keymaker(string):
  string = string.replace(" ", '')
  string = string.replace("?", '')
  string = string.replace(".", '')
  string = string.replace("!", '')
  string = string.replace("/", '')
  string = string.replace(":", '')
  string = string.replace(";", '')
  string = string.replace("'", '')
  string = string.replace("-", '')
  string = string.replace(",", '')
  string = string.lower()
  return string

def updateCache(string, passedTitle, yearVar):
  passedSmallTitle = keymaker(passedTitle)
  imdbID = getImdbID(passedTitle, yearVar)
  with open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'r+') as fp:
    try:
      jsonDict = json.load(fp)
      try:
        if jsonDict[passedSmallTitle]['url'] == string:
          if jsonDict[passedSmallTitle]['status'] == 'Downloaded':
            if checkFiles(passedTitle, yearVar):
              logger.info('{0} from {1} is already downloaded'.format(passedTitle, string))
              return
            else:
              logger.info('{0} from {1} was in the cache but did not exist'.format(passedTitle, string))
              if yearVar == MovieDict[passedTitle]['Trailer Year']:
                videoDownloader(string,passedTitle,yearVar)
              else:
                with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'a+') as temp1:
                  jsonDict[passedSmallTitle]['Trailer Year'] = MovieDict[passedTitle]['Trailer Year']
                  videoDownloader(string,passedTitle,MovieDict[passedTitle]['Trailer Year'])
                  json.dump(jsonDict, temp1, indent=4)
          elif jsonDict[passedSmallTitle]['status'] == 'Released':
            logger.info('{0} from {1} has been released'.format(passedTitle, string))
            return
          else:
            logger.error('error with {0} from {1}'.format(passedTitle, string))
        else:
          logger.info('New trailer for {0}'.format(passedTitle))
          with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'a+') as temp1:
            jsonDict[passedSmallTitle]['url'] = string
            if checkDownloadDate(passedTitle):
              shutil.rmtree(jsonDict[passedSmallTitle]['path'])
              videoDownloader(string, jsonDict[passedSmallTitle]['Movie Title'], yearVar)
              jsonDict[passedSmallTitle]['status'] = 'Downloaded'
            else:
              jsonDict[passedSmallTitle]['status'] = 'Released'
            json.dump(jsonDict, temp1, indent=4)

      except KeyError as e:
        logger.info(e)
        logger.info('Creating New Entry')
        with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'a+') as temp2:
          jsonDict[passedSmallTitle] = MovieDict[passedTitle]
          jsonDict[passedSmallTitle]['path'] = os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
          if checkDownloadDate(passedTitle):
            addToCouchPotato(imdbID)
            videoDownloader(string,passedTitle,yearVar)
            jsonDict[passedSmallTitle]['status'] = 'Downloaded'
          else:
            jsonDict[passedSmallTitle]['status'] = 'Released'
          json.dump(jsonDict, temp2, indent=4)

    except ValueError as e:
      logger.info(e)
      logger.info('Creating Cache')
      jsonDict = {}
      jsonDict['Creation Date'] = currentDate
      jsonDict[passedSmallTitle] = MovieDict[passedTitle]
      jsonDict[passedSmallTitle]['path'] = os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
      if checkDownloadDate(passedTitle):
        addToCouchPotato(imdbID)
        videoDownloader(string, passedTitle, yearVar)
        jsonDict[passedSmallTitle]['status'] = 'Downloaded'
      else:
        jsonDict[passedSmallTitle]['status'] = 'Released'
        json.dump(jsonDict, fp, indent=4)

  if os.path.isfile(os.path.join(cacheDir, 'theaterTrailersTempCache.json')):
    shutil.move(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), os.path.join(cacheDir, 'theaterTrailersCache.json'))


# Downloads the video, names it and copies the resources to the folder
def videoDownloader(string, passedTitle, yearVar):
  # Options for the video downloader
  ydl1_opts = {
    'outtmpl': os.path.join(TheaterTrailersHome, 'Trailers', '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1}).mp4'.format(passedTitle, yearVar)),
    'ignoreerrors': True,
    'format': 'mp4',
  }
  with youtube_dl.YoutubeDL(ydl1_opts) as ydl:
    logger.info("downloading {0} from {1}".format(passedTitle, string))
    ydl.download([string])
    shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1}).mp4'.format(passedTitle, yearVar)),
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1})-trailer.mp4'.format(passedTitle, yearVar))
      )
    shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'), 
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
      )
    updatePlex()


# Downloads info for the videos from the playlist
def infoDownloader(playlist):
  # Options for the info downloader
  ydl_opts = {
    'skip_download': True,
    'ignoreerrors': True,
    'playlistreverse': True,
    'playliststart': 1,
    'playlistend': playlistEndVar,
    'quiet': False,
    'matchtitle': '.*\\btrailer\\b.*', 
    'extract_flat': True,
  }
  with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(playlist)
  
  for x in info['entries']:
    MovieVar = x['title'].encode('ascii',errors='ignore')
    MovieVar = MovieVar.replace(':', '')
    if 'Official' in MovieVar:
      regexedTitle = re.search('^.*(?=(Official))', MovieVar)
    elif 'Trailer' in MovieVar:
      regexedTitle = re.search('.*?(?=Trailer)', MovieVar)
    elif redBand == True:
      if 'Red Band' in MovieVar:
        regexedTitle = re.search('.*?(?=Red)', MovieVar)
    else:
      # Throws out edge cases
      continue
    trailerYear = re.search('(?<=\().*(?=\))', MovieVar)
    TempDict = { 'url' : info['entries'][info['entries'].index(x)]['url']}
    movieTitle = regexedTitle.group(0).strip()
    MovieDict[movieTitle] = TempDict
    MovieDict[movieTitle]['Trailer Release'] = trailerYear.group(0)
    MovieDict[movieTitle]['Movie Title'] = movieTitle
    MovieList.append(movieTitle)


def updatePlex():
  if plexHost == "" or plexPort == "" or plexToken == "":
    return
  else:
    r = requests.get('http://{0}:{1}/library/sections/1/refresh?X-Plex-Token={2}'.format(plexHost, plexPort, plexToken))
    if r.status_code != 200:
      logger.warning("The plex server at {0}:{1} did not respond correctly to the request".format(plexHost, plexPort))

# Returns results from tmdb
def tmdbInfo(item):
  response = search.movie(query=item)
  logger.info("querying the movie db for {0}".format(item))
  time.sleep(pauseRate)
  return search.results
  

def checkFiles(title, year):
  if os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))):
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))):
      shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year)),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))
      )
      updatePlex()
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg')):
      shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'), 
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year))
      )
      updatePlex()
    return True
  if os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))):
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))):
      shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year)),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))
      )
      updatePlex()
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg')):
      shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'), 
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year))
      )
      updatePlex()
    return True
  else:
    return False


# Gets a list of the movies in the directory and removes old movies
def cleanup():
  if not os.path.isdir(os.path.join(TheaterTrailersHome, 'Trailers')):
    return
  else:
    if os.path.isfile(os.path.join(TheaterTrailersHome, 'Trailers', '.DS_Store')):
      os.remove(os.path.join(TheaterTrailersHome, 'Trailers', '.DS_Store'))
    dirsList = os.listdir(os.path.join(TheaterTrailersHome, 'Trailers'))
    for item in dirsList:
      dirsTitle = re.search('^.*(?=(\())', item)
      dirsTitle = dirsTitle.group(0).strip()
      dirsYear = re.search('(?<=\().*(?=\))', item)
      dirsYear = dirsYear.group(0).strip()
      filePath = os.path.join(cacheDir, 'theaterTrailersCache.json')
      if (os.path.isfile(filePath)):
        with open(filePath, 'r') as fp:
          try:
            data = json.load(fp)
            releaseDate = data[keymaker(dirsTitle)]['Release Date']
            if releaseDate <= currentDate:
              logger.info("Removing {0}. Release date has passed".format(dirsTitle))
              shutil.rmtree(os.path.join(TheaterTrailersHome, 'Trailers', '{0} ({1})'.format(dirsTitle, dirsYear)))
              updatePlex()
          except KeyError as ex:
            logger.info(ex)
            logger.info("Removing {0}".format(dirsTitle))
            shutil.rmtree(os.path.join(TheaterTrailersHome, 'Trailers', '{0} ({1})'.format(dirsTitle, dirsYear)))
            updatePlex()
          except ValueError as Ve:
            logger.warning(Ve)
            noCacheCleanup(dirsTitle, dirsYear)      

    
def noCacheCleanup(dirsTitle, dirsYear):
  s = tmdbInfo(dirsTitle)
  for s in search.results:
    releaseDate = s['release_date']
    releaseDateList = releaseDate.split('-')
    if dirsYear == releaseDateList[0]:
      if releaseDate <= currentDate:
        logger.info("Removing {0}".format(dirsTitle))
        shutil.rmtree(os.path.join(TheaterTrailersHome, 'Trailers', '{0} ({1})'.format(dirsTitle, dirsYear)))
        updatePlex()
    
    break    


if __name__ == "__main__":
  main()
