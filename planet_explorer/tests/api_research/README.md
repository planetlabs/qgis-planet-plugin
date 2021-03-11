API Research
=============

Jupyter Notebooks to support API results research

Installation
-------------

Create and activate a new Python 3 virtualenv.

Install Python dependencies:

    (venv) $ pip install -r requirements.txt

Running
--------

To set up the kernel with virtualenv packages, run the following within the
virtualenv:

    (venv) $ python -m ipykernel install --user --name <venv name>
    

After that, start Jupyter:
    
    $ jupyter notebook

From within the Notebook interface, change the kernel (`Kernel --> Change
Kernel --> <name of venv>`) to use the newly created project kernel.
