package main

import "errors"

var errDateTime = errors.New("value is not a date-time under the common grammar")

// checkDateTime is the contract's common date-time grammar: four-digit
// years 0001-9999, valid Gregorian dates, hours 00-23, minutes and seconds
// 00-59, a T or t separator, an optional fraction with at least one digit,
// and Z, z, or a signed HH:MM offset with hours 00-23 and minutes 00-59.
// Only string instances are checked.
func checkDateTime(v any) error {
	s, ok := v.(string)
	if !ok {
		return nil
	}
	if !validDateTime(s) {
		return errDateTime
	}
	return nil
}

// twoDigits reads an ASCII two-digit number at s[i:i+2].
func twoDigits(s string, i int) (int, bool) {
	if i+2 > len(s) || !isDigit(s[i]) || !isDigit(s[i+1]) {
		return 0, false
	}
	return int(s[i]-'0')*10 + int(s[i+1]-'0'), true
}

func daysInMonth(year, month int) int {
	switch month {
	case 2:
		if year%4 == 0 && (year%100 != 0 || year%400 == 0) {
			return 29
		}
		return 28
	case 4, 6, 9, 11:
		return 30
	}
	return 31
}

func validDateTime(s string) bool {
	// YYYY-MM-DDTHH:MM:SS is 19 bytes; at least a Z must follow.
	if len(s) < 20 || s[4] != '-' || s[7] != '-' || (s[10] != 'T' && s[10] != 't') || s[13] != ':' || s[16] != ':' {
		return false
	}
	century, ok1 := twoDigits(s, 0)
	yearLow, ok2 := twoDigits(s, 2)
	month, ok3 := twoDigits(s, 5)
	day, ok4 := twoDigits(s, 8)
	hour, ok5 := twoDigits(s, 11)
	minute, ok6 := twoDigits(s, 14)
	second, ok7 := twoDigits(s, 17)
	if !(ok1 && ok2 && ok3 && ok4 && ok5 && ok6 && ok7) {
		return false
	}
	year := century*100 + yearLow
	if year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month) {
		return false
	}
	if hour > 23 || minute > 59 || second > 59 {
		return false
	}
	rest := s[19:]
	if rest[0] == '.' {
		i := 1
		for i < len(rest) && isDigit(rest[i]) {
			i++
		}
		if i == 1 {
			return false
		}
		rest = rest[i:]
	}
	if rest == "Z" || rest == "z" {
		return true
	}
	if len(rest) != 6 || (rest[0] != '+' && rest[0] != '-') || rest[3] != ':' {
		return false
	}
	offsetHour, ok1 := twoDigits(rest, 1)
	offsetMinute, ok2 := twoDigits(rest, 4)
	return ok1 && ok2 && offsetHour <= 23 && offsetMinute <= 59
}
