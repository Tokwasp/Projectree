package com.ssafy.projectree.global.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class TrimmedSizeValidator implements ConstraintValidator<TrimmedSize, String> {

    private int min;
    private int max;

    @Override
    public void initialize(TrimmedSize constraint) {
        min = constraint.min();
        max = constraint.max();
    }

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (value == null) {
            return true;
        }
        int trimmedLength = value.strip().length();
        return trimmedLength >= min && trimmedLength <= max;
    }
}
