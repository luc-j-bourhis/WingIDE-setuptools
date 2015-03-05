# Various scripts for WingIDE

[WingIDE](http://wingware.com) is a powerful Python IDE with advanced scripting capabilities. This repository aims at collecting scripts I have written for it.

## Distutils panel

This is a panel to run Distutils `setup.py` and to collect errors and warnings. When the "Build" button is pressed, the following command is executed in the directory of the project file:

```
    python -u setup.py build_ext -i
```

where `python` is the Python executable for the current project. It is therefore required that there is a project and that there is a suitable `setup.py` sitting in the directory of that project file. An error dialogue is displayed if it is not so. Then

- build errors are gathered and displayed in a list: clicking one of them opens an editor window displaying the faulty file with the faulty line highlighted;

- the full text output by the build command is also displayed in another tab.

TODO: at the moment, only detects Python errors resulting from an incorrect `setup.py` and [Cython](http://cython.org) errors; C/C++ compiler error patterns are different for different compilers but one can guess the compiler in use by looking at the output of the command above, so it should be possible.
