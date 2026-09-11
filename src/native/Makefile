CXX ?= g++
CXXFLAGS ?= -O3 -fPIC -Wall
WHISPER_INC ?= /usr/include/whisper
WHISPER_LIB ?= -lwhisper

TARGET = ../reaper_notes/libwhisper_easy.so

all: $(TARGET)

$(TARGET): whisper_easy.cpp
	$(CXX) $(CXXFLAGS) -shared -I$(WHISPER_INC) -o $@ $< $(WHISPER_LIB)

clean:
	rm -f $(TARGET)

.PHONY: all clean
