# Urban-Accessibility-through-Milan-s-Piazze-Aperte
A project with a focus on smart cities, assessing accessibility in Milan on top of the project Piazze Aperte.

## File structure 👈
The files here present work synergically.  
The structure of this repository is as follows:  
|- .README.txt  
|- data.zip/  
|   |- raw/  
|   |   |- OpenData/  
|   |   |- OSM/  
|   |   |- overture/  
|   |- preprocessed/  
|   |   |- isochrones/  
|- figures.zip/  
|- 0_sourcecheck.ipynb  
|- 1_preprocessing.ipynb  
|- 2_exploration_visualization.ipynib  
|- 3_isochrones.ipynb  
|- 4_multiindex.ipynb  
|- download_overture_milano.py  
|- isochrones.py  

*Please note* that the dataset of Piazze Aperte was made from scratch by the authors using as source Comune di Milano's official report.

## How to Use the Project 🔍
The notebooks here presented already show the final results presented in the report; however for the sake of reproducibility here are the steps to follow.

1. Download the project folder.
2. Unzip data and figures folders.
3. Run notebooks sequentially; they will automatically call necessary .py files.
4. This will populate data and figures folders.
5. Results can be inspected in the output cells of the notebooks and in the folder figures.

## Authors 👩🏻‍💻
- Chiara Genuardi - c.genuardi1@campus.unimib.it
- Camilla Gentili - c.gentili3@campus.unimib.it
