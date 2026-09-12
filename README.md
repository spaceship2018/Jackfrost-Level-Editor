# Jack Frost Level Editor

Nitronome Jack Frost level editor XML files in
`level_editor/areas/`. 

## Run

```
python level_editor/main.py
or just run the exe from level_editor/main.exe
```

## Build

```
pyinstaller main.py --onefile
```


## How to load created levels

Steps: 

1. Open ruffle swf player in firefox

2. Add the game direct url to ruffle :http://cdn.nitrome.com/games/jackfrost/jackfrost.swf

3. Cntr+Shift+I for web developer options than network tab 

4. Hit reload button

5. Run the game open any level 

6. After openning a level you will see a network request  fetching an xml file from nitrone.com this is the original level file.

7. Right click on the request "set network override" select a location and a filename from areas folder (Here is where the game tries to load the first level from: http://www.nitrome.com/games/jackfrost/areas/178977703c66276066a776a56de3c1a1.xml all urls looks the same just the hashed name changes by level)

8. Next time when the game tries to load that level firefox will serve your choosen xml from areas folder
  
9. Then pause the game and reload the same level which you have been and you are done the game will open your level file.
    


