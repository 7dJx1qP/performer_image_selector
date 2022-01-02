import io
import json
import os
import sys
import PySimpleGUI as sg
from PIL import Image, ImageTk
from stashlib.common import get_timestamp
from stashlib.stash_database import StashDatabase
from stashlib.stash_models import *
import stashlib.log as log
from config import *

def get_img_data(f, maxsize=(1200, 850), first=False, bytes=None):
    """Generate image data using PIL
    """
    if not bytes:
        img = Image.open(f)
    else:
        img = Image.open(io.BytesIO(bytes))
    img.thumbnail(maxsize)
    if first:                     # tkinter is inactive the first time
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        del img
        return bio.getvalue()
    return ImageTk.PhotoImage(img)

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def select_images(db: StashDatabase, outdirs):
    """Loop through actress image folders in <outdir> and display images in folder
    Clicking an image sets the performer to use the image
    """

    tagged_performer_ids = []
    if TAG_NAME:
        tag = db.tags.selectone_name(TAG_NAME)
        if not tag:
            db.tags.insert(TAG_NAME, get_timestamp(), get_timestamp())
        tag = db.tags.selectone_name(TAG_NAME)
        if not tag:
            raise Exception(f"Could not create tag {TAG_NAME}")
        elif SHOW_UNTAGGED_ONLY:
            tagged_performer_ids = [performer_tag.performer_id for performer_tag in db.performers_tags.select_tag_id(tag.id)]

    dirmap = {}
    performers = []
    for outdir in outdirs:
        log.LogInfo(f"Processing {outdir}")
        for r, dirnames, f in os.walk(outdir):
            for dirname in dirnames:
                dirpath = os.path.join(r, dirname)
                performer = db.performers.selectone_name(dirname)
                if performer:
                    if performer.name not in dirmap:
                        dirmap[performer.name] = []
                        performers.append(performer)
                    dirmap[performer.name].append(dirpath)
    
    log.LogTrace(f"FAVORITES_ONLY={FAVORITES_ONLY}")
    performers = [performer for performer in performers if performer.id not in tagged_performer_ids]
    if FAVORITES_ONLY:
        performers = [performer for performer in performers if performer.favorite]

    IMGSIZE = (IMAGE_WIDTH, IMAGE_HEIGHT)
    IMAGES_PER_PAGE = IMAGE_COL_COUNT * IMAGE_ROW_COUNT

    sg.theme('SystemDefaultForReal')
    performer_counter_el = sg.Text("")
    performer_image_el = sg.Image()
    image_counter_el = sg.Text("")
    image_grid = list(chunks([sg.Image(enable_events=True, key=f"image_select_{i}") for i in range(0, IMAGES_PER_PAGE)], IMAGE_COL_COUNT))
    layout = [
        [
            performer_counter_el,
        ],
        [
            sg.Submit(button_text='Back', key='performer_back'), sg.Submit(button_text='Next', key='performer_next'),
            sg.Input(size=5, justification='right', default_text="1", key='performer_go_to_num'),
            sg.Submit(button_text='Go To', key='performer_go_to'),
            sg.Submit(button_text='Skip', key='performer_skip')
        ],
        [
            performer_image_el
        ],
        [
            image_counter_el,
        ],
        [
            sg.Submit(button_text='Back', key='image_back'), sg.Submit(button_text='Next', key='image_next')
        ],
        [
            sg.Text("Click an image below to set it as the performer image"),
        ],
    ] + image_grid

    window = sg.Window('Performer Image Selector', layout=layout, size=(IMAGE_COL_COUNT * IMAGE_WIDTH + 100, IMAGE_ROW_COUNT * IMAGE_HEIGHT + IMAGE_HEIGHT + 200), resizable=True,  return_keyboard_events=True, finalize=True)

    def clear_images():
        for row in range(0, IMAGE_ROW_COUNT):
            image_row = image_grid[row]
            for col in range(0, IMAGE_COL_COUNT):
                image = image_row[col]
                image.update()

    def set_image_page(image_pages, page_index):
        clear_images()
        image_counter_el.update(f"Image page {page_index + 1} of {len(image_pages)}")
        image_page_grid = list(chunks(image_pages[page_index], IMAGE_COL_COUNT))
        for row_index in range(0, len(image_page_grid)):
            image_page_grid_row = image_page_grid[row_index]
            for col_index in range(0, len(image_page_grid_row)):
                filepath = image_page_grid_row[col_index]
                image_grid_el = image_grid[row_index][col_index]
                image_grid_el.update(data=get_img_data(filepath, maxsize=IMGSIZE, first=True))

    def set_performer(performer_index):
        performer_index = performer_index % len(performers)
        performer = performers[performer_index]

        window['performer_go_to_num'].update(performer_index + 1)
        performer_counter_el.update(f"{performer_index + 1} of {len(performers)} {performer.name}")

        performer_image = db.performers_image.selectone_performer_id(performer.id)
        if performer_image:
            performer_image_el.update(data=get_img_data(None, bytes=performer_image.image, maxsize=IMGSIZE, first=True))
        else:
            performer_image_el.update()

        clear_images()
        
        image_files = []
        for dirpath in dirmap[performer.name]:
            for file in os.listdir(dirpath):
                filepath = os.path.join(dirpath, file)
                image_files.append(filepath)

        image_pages = list(chunks(image_files, IMAGES_PER_PAGE))
        if image_pages:
            set_image_page(image_pages, 0)

        return performer_index, performer, image_pages, 0

    performer_index, performer, image_pages, image_page_index = set_performer(0)
    
    def tag_performer():
        if tag and TAG_PERFORMERS:
            tag_ids = [performer_tag.tag_id for performer_tag in db.performers_tags.select_performer_id(performer.id)]
            if tag.id not in tag_ids:
                db.performers_tags.insert(performer.id, tag.id)
                log.LogInfo(f'Tagged {performer.name} {tag.name}')
            else:
                log.LogInfo(f'Performer {performer.name} already tagged {tag.name}')

    while True:
        event, values = window.read()
        if event:
            log.LogInfo(event)
        if event in (sg.WIN_CLOSED, 'Exit'):
            sys.exit(0)
        elif event == 'Cancel':
            sys.exit(0)
        elif event == 'performer_back' or event == 'Left:37' or event == 'a':
            performer_index, performer, image_pages, image_page_index = set_performer(performer_index - 1)
        elif event == 'performer_next' or event == 'Right:39' or event == 'd':
            performer_index, performer, image_pages, image_page_index = set_performer(performer_index + 1)
        elif event == 'performer_go_to':
            if values['performer_go_to_num'].isnumeric():
                performer_index, performer, image_pages, image_page_index = set_performer(int(values['performer_go_to_num']) - 1)
            else:
                window['performer_go_to_num'].update(performer_index + 1)
        elif event == 'image_back':
            image_page_index = (image_page_index - 1) % len(image_pages)
            set_image_page(image_pages, image_page_index)
        elif event == 'image_next':
            image_page_index = (image_page_index + 1) % len(image_pages)
            set_image_page(image_pages, image_page_index)
        elif event.startswith('image_select_'):
            filepath = image_pages[image_page_index][int(event.removeprefix('image_select_'))]
            with open(filepath, 'rb') as f:
                imgbytes = f.read()
                performer_image = db.performers_image.selectone_performer_id(performer.id)
                if performer_image:
                    db.execute("""UPDATE performers_image SET image = ? WHERE performer_id = ?""", (imgbytes, performer.id))
                else:
                    db.performers_image.insert(performer.id, imgbytes)
                log.LogInfo(f'Set {performer.name} image to {filepath}')
                tag_performer()
                performer_index, performer, image_pages, image_page_index = set_performer(performer_index + 1)
        elif event == 'performer_skip':
            tag_performer()
            performer_index, performer, image_pages, image_page_index = set_performer(performer_index + 1)

def read_json_input():
    json_input = sys.stdin.read()
    return json.loads(json_input)
    
json_input = read_json_input()
mode_arg = json_input['args']['mode']

try:
    db = StashDatabase(DATABASE_PATH)
except Exception as e:
    log.LogError(str(e))
    sys.exit(0)

try:
    log.LogInfo("mode: {}".format(mode_arg))

    if mode_arg == 'select_images':
        select_images(db, IMAGE_DIRECTORIES)

except Exception as e:
    log.LogError(str(e))

db.close()

log.LogInfo('done')
output = {}
output["output"] = "ok"
out = json.dumps(output)
print(out + "\n")